import csv, io
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from collections import defaultdict
from typing import Iterable
D = Decimal

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

def parse_expenses_csv(data: bytes) -> list[Expense]:
    text = data.decode("utf-8-sig")
    try: dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\\t")
    except csv.Error: dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames: raise ValueError("CSV-файл пуст или не содержит заголовков.")
    aliases = {"amount":{"amount","sum","сумма","стоимость"},"category":{"category","категория","mcc_category","тип"},"description":{"description","описание","merchant","магазин","операция"},"date":{"date","дата"}}
    normalized = {str(k).strip().lower():k for k in reader.fieldnames if k}
    cols = {target:next((normalized[n] for n in names if n in normalized),None) for target,names in aliases.items()}
    if not cols["amount"] or not cols["category"]: raise ValueError("Нужны столбцы суммы и категории.")
    out=[]
    for no,row in enumerate(reader,2):
        raw=(row.get(cols["amount"]) or "").strip().replace(" ","").replace(",", ".")
        try: amount=D(raw)
        except Exception as e: raise ValueError(f"Некорректная сумма в строке {no}.") from e
        cat=(row.get(cols["category"]) or "").strip()
        if amount>0 and cat: out.append(Expense(amount,cat,(row.get(cols["description"]) or "").strip(),(row.get(cols["date"]) or "").strip()))
    return out

def evaluate_rule(expenses: Iterable[Expense], rule: CashbackRule) -> CashbackResult:
    eligible=D(0); cashback=D(0); excluded=tuple(x.casefold() for x in rule.excluded_keywords)
    monthly=defaultdict(lambda:D(0))
    for item in expenses:
        if item.category.casefold()!=rule.category.casefold() or item.amount<rule.min_purchase or (rule.max_purchase is not None and item.amount>rule.max_purchase): continue
        if any(k in f"{item.description} {item.category}".casefold() for k in excluded): continue
        eligible += item.amount
        month=item.date[:7] if len(item.date)>=7 else "unknown"
        monthly[month] += (item.amount*rule.rate_percent/D(100)).quantize(D("0.01"),rounding=ROUND_DOWN)
    cashback=sum((min(v,rule.monthly_cap) if rule.monthly_cap is not None else v for v in monthly.values()),D(0))
    return CashbackResult(rule.category,eligible,cashback,D(0))

def compare_rules(expenses: Iterable[Expense], rules: list[CashbackRule]) -> list[CashbackResult]:
    expenses=list(expenses); results=[evaluate_rule(expenses,r) for r in rules]
    best={}
    for x in results: best[x.category.casefold()]=max(best.get(x.category.casefold(),D(0)),x.cashback)
    return sorted([CashbackResult(x.category,x.eligible_spend,x.cashback,max(D(0),best[x.category.casefold()]-x.cashback)) for x in results],key=lambda x:x.cashback,reverse=True)
