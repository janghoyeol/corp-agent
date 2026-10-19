from datetime import date

from corp_agent.agent import latest_annual_bsns_year


def test_latest_annual_bsns_year_after_q1():
    assert latest_annual_bsns_year(date(2026, 10, 19)) == "2025"


def test_latest_annual_bsns_year_before_q2():
    assert latest_annual_bsns_year(date(2026, 2, 1)) == "2024"


def test_latest_annual_bsns_year_year_boundary():
    assert latest_annual_bsns_year(date(2026, 3, 31)) == "2024"
    assert latest_annual_bsns_year(date(2026, 4, 1)) == "2025"
