from decimal import Decimal as D
from finsmart.cashback import Expense, CashbackRule, evaluate_rule, parse_expenses_csv

def test_csv_parser_semicolon_and_russian_headers():
    rows=parse_expenses_csv("дата;сумма;категория\\n2026-10-01;1000;Супермаркеты\\n".encode())
    assert len(rows)==1 and rows[0].amount==D("1000")

def test_cashback_cap_applies_per_month():
    expenses=[Expense(D("1000"),"Еда","","2026-10-01"),Expense(D("1000"),"Еда","","2026-10-02")]
    rule=CashbackRule("5%","Еда",D("5"),monthly_cap=D("60"))
    assert evaluate_rule(expenses,rule).cashback==D("60.00")
