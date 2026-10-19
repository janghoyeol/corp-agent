from corp_agent import tools as corp_tools
from corp_agent.corp_codes import CorpCode
from corp_agent.dart_client import DartNoDataError


class FakeDartClient:
    """CFS 조회시 013(데이터 없음)을 내고 OFS는 실데이터를 주는 폴백 시나리오용."""

    def __init__(self, cfs_rows=None, ofs_rows=None, cfs_raises=False):
        self.cfs_rows = cfs_rows
        self.ofs_rows = ofs_rows
        self.cfs_raises = cfs_raises
        self.calls: list[str] = []

    def get_financials(self, corp_code, bsns_year, reprt_code="11011", fs_div="CFS"):
        self.calls.append(fs_div)
        if fs_div == "CFS" and self.cfs_raises:
            raise DartNoDataError("013", "조회된 데이타가 없습니다.")
        return self.cfs_rows if fs_div == "CFS" else self.ofs_rows


def _row(account_nm, amount, sj_div="IS"):
    return {"account_nm": account_nm, "thstrm_amount": amount, "sj_div": sj_div}


def test_get_financials_uses_cfs_when_available():
    rows = [_row("매출액", "1,000"), _row("영업이익", "100")]
    client = FakeDartClient(cfs_rows=rows)
    result = corp_tools.get_financials(client, "00126380", "2023")
    assert result["fs_div"] == "CFS"
    assert result["accounts"]["매출액"]["amount"] == 1000


def test_get_financials_falls_back_to_ofs_on_013():
    ofs_rows = [_row("매출액", "500")]
    client = FakeDartClient(cfs_raises=True, ofs_rows=ofs_rows)
    result = corp_tools.get_financials(client, "00126380", "2023")
    assert result["fs_div"] == "OFS"
    assert client.calls == ["CFS", "OFS"]
    assert result["accounts"]["매출액"]["amount"] == 500


def test_get_financials_account_alias_matching():
    rows = [_row("수익(매출액)", "2,000")]
    client = FakeDartClient(cfs_rows=rows)
    result = corp_tools.get_financials(client, "00126380", "2023", accounts=["매출액"])
    assert result["accounts"]["매출액"]["account_nm"] == "수익(매출액)"
    assert result["accounts"]["매출액"]["amount"] == 2000


def test_get_financials_missing_account_is_none_not_fabricated():
    rows = [_row("매출액", "1,000")]
    client = FakeDartClient(cfs_rows=rows)
    result = corp_tools.get_financials(
        client, "00126380", "2023", accounts=["매출액", "영업이익"]
    )
    assert result["accounts"]["영업이익"] is None


def test_get_financials_distinguishes_bs_vs_is_accounts():
    # 자산총계는 재무상태표(BS) 행만 매치해야 한다. sj_div가 다르면 매치되면 안 됨.
    rows = [_row("자산총계", "999", sj_div="IS")]
    client = FakeDartClient(cfs_rows=rows)
    result = corp_tools.get_financials(client, "00126380", "2023", accounts=["자산총계"])
    assert result["accounts"]["자산총계"] is None


def test_compute_growth_basic():
    values = [
        {"year": "2021", "amount": 100},
        {"year": "2022", "amount": 150},
        {"year": "2023", "amount": 120},
    ]
    result = corp_tools.compute_growth(values)
    assert result[0]["yoy_growth_pct"] is None
    assert result[1]["yoy_growth_pct"] == 50.0
    assert result[2]["yoy_growth_pct"] == -20.0


def test_compute_growth_sorts_unordered_input():
    values = [
        {"year": "2023", "amount": 120},
        {"year": "2021", "amount": 100},
        {"year": "2022", "amount": 150},
    ]
    result = corp_tools.compute_growth(values)
    assert [v["year"] for v in result] == ["2021", "2022", "2023"]


def test_compute_growth_handles_zero_base():
    values = [{"year": "2021", "amount": 0}, {"year": "2022", "amount": 100}]
    result = corp_tools.compute_growth(values)
    assert result[1]["yoy_growth_pct"] is None  # 0으로 나눌 수 없음 — None으로 명시


def test_resolve_company_wraps_corp_codes():
    corps = [CorpCode("00126380", "삼성전자", "005930", "20250101")]
    result = corp_tools.resolve_company("삼성전자", corps)
    assert result[0]["corp_code"] == "00126380"
    assert result[0]["is_listed"] is True
