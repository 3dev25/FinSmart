from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
D=Decimal
CENT=D("0.01")
def money(x): return x.quantize(CENT,rounding=ROUND_HALF_UP)
@dataclass(frozen=True)
class Loan:
    principal: Decimal
    annual_rate_percent: Decimal
    months: int
    def validate(self):
        if self.principal<=0 or self.annual_rate_percent<0 or not 1<=self.months<=600: raise ValueError("Проверьте сумму, ставку и срок кредита.")
@dataclass(frozen=True)
class Payment:
    month:int; payment:Decimal; principal:Decimal; interest:Decimal; balance:Decimal
@dataclass(frozen=True)
class Schedule:
    payments:tuple[Payment,...]; total_interest:Decimal; total_paid:Decimal; final_month:int; monthly_payment:Decimal
def annuity_payment(principal,annual_rate_percent,months):
    if principal<=0 or months<=0: raise ValueError("Сумма и срок должны быть положительными.")
    r=annual_rate_percent/D("1200")
    if r==0:return money(principal/D(months))
    f=(D(1)+r)**months
    return money(principal*r*f/(f-D(1)))
def build_schedule(loan,extra_by_month=None,reduce_term=True):
    loan.validate(); extra_by_month=extra_by_month or {}; r=loan.annual_rate_percent/D("1200")
    regular=annuity_payment(loan.principal,loan.annual_rate_percent,loan.months); balance=loan.principal; rows=[]; ti=D(0); tp=D(0)
    for month in range(1,loan.months+601):
        interest=money(balance*r); due=min(balance,regular-interest); extra=max(D(0),extra_by_month.get(month,D(0))); principal=min(balance,due+extra); payment=money(interest+principal); balance=max(D(0),balance-principal); ti+=interest; tp+=payment
        rows.append(Payment(month,payment,money(principal),interest,money(balance)))
        if balance<=D("0.005") or (not reduce_term and month>=loan.months):break
    return Schedule(tuple(rows),money(ti),money(tp),len(rows),regular)
@dataclass(frozen=True)
class PrepaymentComparison:
    baseline:Schedule; reduce_term:Schedule; reduce_payment:Schedule; interest_saved_term:Decimal; interest_saved_payment:Decimal
def compare_prepayment(loan,extra_monthly,first_extra_month=1):
    loan.validate()
    if extra_monthly<0 or first_extra_month<1: raise ValueError("Некорректная доплата.")
    base=build_schedule(loan); extra={m:extra_monthly for m in range(first_extra_month,loan.months+1)}
    term=build_schedule(loan,extra,True)
    # Recalculate required annuity after each extra payment, keeping the original final month.
    balance=loan.principal; r=loan.annual_rate_percent/D("1200"); rows=[]; ti=D(0); tp=D(0)
    for month in range(1,loan.months+1):
        interest=money(balance*r); remaining=loan.months-month+1; regular=annuity_payment(balance,loan.annual_rate_percent,remaining)
        due=min(balance,max(D(0),regular-interest)); extra_now=extra_monthly if month>=first_extra_month else D(0); principal=min(balance,due+extra_now); pay=money(interest+principal); balance=max(D(0),balance-principal); ti+=interest; tp+=pay; rows.append(Payment(month,pay,money(principal),interest,money(balance)))
        if balance<=D("0.005"):break
    reduced=Schedule(tuple(rows),money(ti),money(tp),len(rows),base.monthly_payment)
    return PrepaymentComparison(base,term,reduced,money(base.total_interest-term.total_interest),money(base.total_interest-reduced.total_interest))
@dataclass(frozen=True)
class RefinanceResult:
    current_total:Decimal; new_total:Decimal; net_saving:Decimal; break_even_month:int|None; current_schedule:Schedule; new_schedule:Schedule
def compare_refinance(current_balance,current_rate,current_months,new_rate,new_months,fees=D(0),insurance=D(0),monthly_fee=D(0)):
    current=build_schedule(Loan(current_balance,current_rate,current_months)); new=build_schedule(Loan(current_balance,new_rate,new_months)); current_cost=current.total_paid; new_cost=new.total_paid+fees+insurance+monthly_fee*D(new_months)
    old=D(0); fresh=fees+insurance; be=0 if fresh<=0 else None
    for i in range(max(len(current.payments),len(new.payments))):
        if i<len(current.payments):old+=current.payments[i].payment
        if i<len(new.payments):fresh+=new.payments[i].payment+monthly_fee
        if be is None and fresh<=old:be=i+1
    return RefinanceResult(money(current_cost),money(new_cost),money(current_cost-new_cost),be,current,new)
