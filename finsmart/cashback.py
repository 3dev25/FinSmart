import csv
import io
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Iterable

D = Decimal
CENT = D("0.01")


@dataclass(frozen=True)
class Expense:
    amount: Decimal
    category: str
    description: str = ""
    date: str = ""


@dataclass(frozen=True)
class CashbackRule:
    name: str
    category: str
    rate_percent: Decimal
    monthly_cap: Decimal | None = None
    min_purchase: Decimal = D(0)
    max_purchase: Decimal | None = None
    excluded_keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class CashbackResult:
    category: str
    eligible_spend: Decimal
    cashback: Decimal
    lost_cashback: Decimal


def _validate_rule(rule: CashbackRule):
    rate = D(str(rule.rate_percent))
    minimum = D(str(rule.min_purchase))
    if not rule.category.strip() or rate < 0 or rate > 100 or minimum < 0:
        raise ValueError("Проверьте категорию, ставку (0–100%) и минимальную покупку.")
    if rule.monthly_cap is not None and D(str(rule.monthly_cap)) < 0:
        raise ValueError("Месячный лимит не может быть отрицательным.")
    if rule.max_purchase is not None and D(str(rule.max_purchase)) < minimum:
        raise ValueError("Максимальная покупка не может быть меньше минимальной.")


def parse_expenses_csv(data: bytes) -> list[Expense]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV должен быть в кодировке UTF-8.") from exc

    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("CSV-файл пуст или не содержит заголовков.")

    aliases = {
        "amount": {"amount", "sum", "сумма", "стоимость"},
        "category": {"category", "категория", "mcc_category", "тип"},
        "description": {"description", "описание", "merchant", "магазин", "операция"},
        "date": {"date", "дата"},
    }
    normalized = {str(key).strip().lower(): key for key in reader.fieldnames if key}
    columns = {
        target: next((normalized[name] for name in names if name in normalized), None)
        for target, names in aliases.items()
    }
    if not columns["amount"] or not columns["category"]:
        raise ValueError("Нужны столбцы суммы и категории.")

    expenses = []
    for line_number, row in enumerate(reader, 2):
        raw = (row.get(columns["amount"]) or "").strip().replace(" ", "").replace(",", ".")
        try:
            amount = D(raw)
        except Exception as exc:
            raise ValueError(f"Некорректная сумма в строке {line_number}.") from exc
        if not amount.is_finite():
            raise ValueError(f"Некорректная сумма в строке {line_number}.")
        category = (row.get(columns["category"]) or "").strip()
        if amount > 0 and category:
            expenses.append(Expense(
                amount=amount,
                category=category,
                description=(row.get(columns["description"]) or "").strip(),
                date=(row.get(columns["date"]) or "").strip(),
            ))
    return expenses


def evaluate_rule(expenses: Iterable[Expense], rule: CashbackRule) -> CashbackResult:
    _validate_rule(rule)
    eligible_spend = D(0)
    monthly_cashback = defaultdict(lambda: D(0))
    excluded = tuple(keyword.casefold() for keyword in rule.excluded_keywords if keyword)

    for item in expenses:
        amount = D(str(item.amount))
        if amount <= 0 or item.category.casefold() != rule.category.casefold():
            continue
        if amount < rule.min_purchase:
            continue
        if rule.max_purchase is not None and amount > rule.max_purchase:
            continue
        searchable = f"{item.description} {item.category}".casefold()
        if any(keyword in searchable for keyword in excluded):
            continue

        eligible_spend += amount
        month = item.date[:7] if len(item.date) >= 7 else "unknown"
        transaction_cashback = (amount * rule.rate_percent / D(100)).quantize(
            CENT, rounding=ROUND_DOWN
        )
        monthly_cashback[month] += transaction_cashback

    cashback = sum(
        (
            min(value, rule.monthly_cap)
            if rule.monthly_cap is not None else value
            for value in monthly_cashback.values()
        ),
        D(0),
    )
    return CashbackResult(rule.category, eligible_spend, cashback.quantize(CENT), D(0))


def compare_rules(expenses: Iterable[Expense], rules: list[CashbackRule]) -> list[CashbackResult]:
    expenses = list(expenses)
    results = [evaluate_rule(expenses, rule) for rule in rules]
    best_by_category = {}
    for result in results:
        key = result.category.casefold()
        best_by_category[key] = max(best_by_category.get(key, D(0)), result.cashback)

    compared = [
        CashbackResult(
            result.category,
            result.eligible_spend,
            result.cashback,
            max(D(0), best_by_category[result.category.casefold()] - result.cashback),
        )
        for result in results
    ]
    return sorted(compared, key=lambda result: result.cashback, reverse=True)
