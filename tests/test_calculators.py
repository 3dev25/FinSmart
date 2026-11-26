from decimal import Decimal as D

import pytest

from finsmart.calculators import (
    Loan, annuity_payment, build_schedule, compare_prepayment, compare_refinance
)


def test_zero_interest_payment():
    assert annuity_payment(D("12000"), D("0"), 12) == D("1000.00")


def test_schedule_pays_off():
    schedule = build_schedule(Loan(D("100000"), D("12"), 12))
    assert schedule.final_month == 12
    assert schedule.payments[-1].balance == D("0.00")
    assert schedule.total_interest > 0


def test_extra_payment_saves_interest_and_shortens_term():
    result = compare_prepayment(Loan(D("300000"), D("18"), 36), D("5000"))
    assert result.interest_saved_term > 0
    assert result.reduce_term.final_month < result.baseline.final_month
    assert result.interest_saved_payment > 0
    assert result.reduce_payment.final_month <= result.baseline.final_month


def test_reduced_payment_keeps_original_maturity_when_no_extra():
    result = compare_prepayment(Loan(D("300000"), D("18"), 36), D("0"))
    assert result.reduce_payment.final_month == 36
    assert abs(result.reduce_payment.total_interest - result.baseline.total_interest) <= D("0.02")


def test_refinance_costs_and_break_even_are_included():
    result = compare_refinance(
        D("200000"), D("20"), 36, D("12"), 36, D("10000"), D("5000")
    )
    assert result.new_total > result.new_schedule.total_paid
    assert result.net_saving == result.current_total - result.new_total
    assert result.break_even_month is not None


def test_refinance_without_costs_breaks_even_immediately():
    result = compare_refinance(D("100000"), D("10"), 24, D("8"), 24)
    assert result.break_even_month == 0


def test_invalid_loan_is_rejected():
    with pytest.raises(ValueError):
        build_schedule(Loan(D("0"), D("10"), 12))


def test_negative_refinance_cost_is_rejected():
    with pytest.raises(ValueError):
        compare_refinance(D("100000"), D("10"), 24, D("8"), 24, fees=D("-1"))
