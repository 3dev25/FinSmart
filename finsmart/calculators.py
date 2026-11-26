from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

D = Decimal
CENT = D("0.01")
ZERO = D("0")


def as_decimal(value) -> Decimal:
    return value if isinstance(value, Decimal) else D(str(value))


def money(value: Decimal) -> Decimal:
    return as_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Loan:
    principal: Decimal
    annual_rate_percent: Decimal
    months: int

    def validate(self):
        principal = as_decimal(self.principal)
        rate = as_decimal(self.annual_rate_percent)
        if principal <= ZERO or rate < ZERO or rate > D("1000") or not 1 <= self.months <= 600:
            raise ValueError("Проверьте сумму, ставку (0–1000%) и срок кредита (1–600 месяцев).")


@dataclass(frozen=True)
class Payment:
    month: int
    payment: Decimal
    principal: Decimal
    interest: Decimal
    balance: Decimal


@dataclass(frozen=True)
class Schedule:
    payments: tuple[Payment, ...]
    total_interest: Decimal
    total_paid: Decimal
    final_month: int
    monthly_payment: Decimal


def annuity_payment(principal, annual_rate_percent, months):
    principal = as_decimal(principal)
    rate = as_decimal(annual_rate_percent)
    if principal <= ZERO or months <= 0:
        raise ValueError("Сумма и срок должны быть положительными.")
    if rate < ZERO:
        raise ValueError("Ставка не может быть отрицательной.")
    monthly_rate = rate / D("1200")
    if monthly_rate == ZERO:
        return money(principal / D(months))
    factor = (D(1) + monthly_rate) ** months
    return money(principal * monthly_rate * factor / (factor - D(1)))


def build_schedule(loan: Loan, extra_by_month=None, reduce_term=True):
    loan.validate()
    extra_by_month = extra_by_month or {}
    principal = as_decimal(loan.principal)
    rate = as_decimal(loan.annual_rate_percent)
    monthly_rate = rate / D("1200")
    regular_payment = annuity_payment(principal, rate, loan.months)
    balance = principal
    rows = []
    total_interest = ZERO
    total_paid = ZERO

    for month in range(1, loan.months + 601):
        interest = money(balance * monthly_rate)
        scheduled_principal = max(ZERO, regular_payment - interest)
        extra = max(ZERO, as_decimal(extra_by_month.get(month, ZERO)))
        principal_paid = min(balance, scheduled_principal + extra)
        payment = money(interest + principal_paid)
        balance = max(ZERO, balance - principal_paid)
        total_interest += interest
        total_paid += payment
        rows.append(Payment(month, payment, money(principal_paid), interest, money(balance)))
        if balance <= D("0.005") or (not reduce_term and month >= loan.months):
            break

    return Schedule(
        tuple(rows), money(total_interest), money(total_paid),
        len(rows), regular_payment
    )


@dataclass(frozen=True)
class PrepaymentComparison:
    baseline: Schedule
    reduce_term: Schedule
    reduce_payment: Schedule
    interest_saved_term: Decimal
    interest_saved_payment: Decimal


def _reduced_payment_schedule(loan: Loan, extra_monthly: Decimal, first_extra_month: int):
    balance = as_decimal(loan.principal)
    rate = as_decimal(loan.annual_rate_percent)
    monthly_rate = rate / D("1200")
    rows = []
    total_interest = ZERO
    total_paid = ZERO

    for month in range(1, loan.months + 1):
        remaining_months = loan.months - month + 1
        # The required instalment is recalculated against the remaining balance
        # and original maturity. The voluntary extra is then applied to principal.
        regular = annuity_payment(balance, rate, remaining_months)
        interest = money(balance * monthly_rate)
        scheduled_principal = max(ZERO, regular - interest)
        extra = extra_monthly if month >= first_extra_month else ZERO
        principal_paid = min(balance, scheduled_principal + extra)
        payment = money(interest + principal_paid)
        balance = max(ZERO, balance - principal_paid)
        total_interest += interest
        total_paid += payment
        rows.append(Payment(month, payment, money(principal_paid), interest, money(balance)))
        if balance <= D("0.005"):
            break

    return Schedule(tuple(rows), money(total_interest), money(total_paid), len(rows),
                    annuity_payment(loan.principal, rate, loan.months))


def compare_prepayment(loan: Loan, extra_monthly, first_extra_month=1):
    loan.validate()
    extra_monthly = as_decimal(extra_monthly)
    if extra_monthly < ZERO or not 1 <= first_extra_month <= loan.months:
        raise ValueError("Некорректная сумма или месяц начала досрочных платежей.")
    baseline = build_schedule(loan)
    extra_by_month = {
        month: extra_monthly
        for month in range(first_extra_month, loan.months + 1)
    }
    shorter = build_schedule(loan, extra_by_month, reduce_term=True)
    lower_payment = _reduced_payment_schedule(loan, extra_monthly, first_extra_month)
    return PrepaymentComparison(
        baseline,
        shorter,
        lower_payment,
        money(baseline.total_interest - shorter.total_interest),
        money(baseline.total_interest - lower_payment.total_interest),
    )


@dataclass(frozen=True)
class RefinanceResult:
    current_total: Decimal
    new_total: Decimal
    net_saving: Decimal
    break_even_month: int | None
    current_schedule: Schedule
    new_schedule: Schedule


def compare_refinance(
    current_balance, current_rate, current_months,
    new_rate, new_months, fees=ZERO, insurance=ZERO, monthly_fee=ZERO
):
    fees = as_decimal(fees)
    insurance = as_decimal(insurance)
    monthly_fee = as_decimal(monthly_fee)
    if min(fees, insurance, monthly_fee) < ZERO:
        raise ValueError("Комиссии, страховка и ежемесячные расходы не могут быть отрицательными.")

    current_loan = Loan(as_decimal(current_balance), as_decimal(current_rate), current_months)
    new_loan = Loan(as_decimal(current_balance), as_decimal(new_rate), new_months)
    current = build_schedule(current_loan)
    new = build_schedule(new_loan)

    current_total = current.total_paid
    new_total = money(new.total_paid + fees + insurance + monthly_fee * D(new_months))

    # Expenses for the new loan include one-off costs at month zero.
    # Break-even is the first month when cumulative new-loan outflow
    # becomes no greater than cumulative payments on the existing loan.
    old_cumulative = ZERO
    new_cumulative = fees + insurance
    break_even = 0 if new_cumulative == ZERO else None
    horizon = max(len(current.payments), len(new.payments))

    for index in range(horizon):
        if index < len(current.payments):
            old_cumulative += current.payments[index].payment
        if index < len(new.payments):
            new_cumulative += new.payments[index].payment + monthly_fee
        if break_even is None and new_cumulative <= old_cumulative:
            break_even = index + 1

    return RefinanceResult(
        money(current_total), new_total, money(current_total - new_total),
        break_even, current, new
    )
