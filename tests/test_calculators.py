from decimal import Decimal as D
from finsmart.calculators import Loan,annuity_payment,build_schedule,compare_prepayment,compare_refinance

def test_zero_interest_payment(): assert annuity_payment(D("12000"),D("0"),12)==D("1000.00")
def test_schedule_pays_off():
    s=build_schedule(Loan(D("100000"),D("12"),12)); assert s.final_month==12 and s.payments[-1].balance==D("0.00") and s.total_interest>0
def test_extra_payment_saves_interest():
    c=compare_prepayment(Loan(D("300000"),D("18"),36),D("5000")); assert c.interest_saved_term>0 and c.reduce_term.final_month<c.baseline.final_month
def test_refinance_costs_are_included():
    r=compare_refinance(D("200000"),D("20"),36,D("12"),36,D("10000"),D("5000")); assert r.new_total>r.new_schedule.total_paid and r.net_saving==r.current_total-r.new_total
