from decimal import Decimal as D

import pytest

from finsmart.cashback import (
    Expense, CashbackRule, evaluate_rule, parse_expenses_csv, compare_rules
)


def test_csv_parser_semicolon_and_russian_headers():
    rows = parse_expenses_csv(
        "дата;сумма;категория\n2026-10-01;1000;Супермаркеты\n".encode()
    )
    assert len(rows) == 1
    assert rows[0].amount == D("1000")
    assert rows[0].category == "Супермаркеты"


def test_cashback_cap_applies_per_month():
    expenses = [
        Expense(D("1000"), "Еда", "", "2026-10-01"),
        Expense(D("1000"), "Еда", "", "2026-10-02"),
    ]
    rule = CashbackRule("5%", "Еда", D("5"), monthly_cap=D("60"))
    assert evaluate_rule(expenses, rule).cashback == D("60.00")


def test_excluded_keywords_and_purchase_limits():
    expenses = [
        Expense(D("1000"), "Еда", "Обычный магазин", "2026-10-01"),
        Expense(D("500"), "Еда", "Алкоголь", "2026-10-02"),
        Expense(D("50"), "Еда", "Маленькая покупка", "2026-10-03"),
    ]
    rule = CashbackRule(
        "rule", "Еда", D("10"), min_purchase=D("100"),
        excluded_keywords=("алкоголь",)
    )
    result = evaluate_rule(expenses, rule)
    assert result.eligible_spend == D("1000")
    assert result.cashback == D("100.00")


def test_compare_rules_reports_difference_within_category():
    expenses = [Expense(D("10000"), "Еда", "", "2026-10-01")]
    rules = [
        CashbackRule("A", "Еда", D("1")),
        CashbackRule("B", "Еда", D("5")),
    ]
    results = compare_rules(expenses, rules)
    assert results[0].cashback == D("500.00")
    assert results[1].lost_cashback == D("400.00")


def test_invalid_cashback_rate_is_rejected():
    with pytest.raises(ValueError):
        evaluate_rule([], CashbackRule("bad", "Еда", D("101")))


def test_invalid_csv_encoding_has_clear_error():
    with pytest.raises(ValueError, match="UTF-8"):
        parse_expenses_csv(b"\xff\xfe\x00")
