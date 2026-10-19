from pathlib import Path

from corp_agent.corp_codes import load_tsv, parse_corp_code_xml, resolve_company, write_tsv

SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<result>
  <list>
    <corp_code>00126380</corp_code>
    <corp_name>\xec\x82\xbc\xec\x84\xb1\xec\xa0\x84\xec\x9e\x90</corp_name>
    <stock_code>005930</stock_code>
    <modify_date>20250101</modify_date>
  </list>
  <list>
    <corp_code>00164779</corp_code>
    <corp_name>\xec\x82\xbc\xec\x84\xb1\xec\xa0\x84\xec\x9e\x90\xec\x84\x9c\xeb\xb9\x84\xec\x8a\xa4</corp_name>
    <stock_code></stock_code>
    <modify_date>20250101</modify_date>
  </list>
  <list>
    <corp_code>00401731</corp_code>
    <corp_name>\xec\xb9\xb4\xec\xb9\xb4\xec\x98\xa4</corp_name>
    <stock_code>035720</stock_code>
    <modify_date>20250101</modify_date>
  </list>
</result>
"""


def test_parse_corp_code_xml():
    corps = parse_corp_code_xml(SAMPLE_XML)
    assert len(corps) == 3
    samsung = next(c for c in corps if c.corp_name == "삼성전자")
    assert samsung.corp_code == "00126380"
    assert samsung.is_listed


def test_unlisted_company_has_no_stock_code():
    corps = parse_corp_code_xml(SAMPLE_XML)
    service = next(c for c in corps if c.corp_name == "삼성전자서비스")
    assert not service.is_listed


def test_resolve_company_exact_match_first():
    corps = parse_corp_code_xml(SAMPLE_XML)
    results = resolve_company("삼성전자", corps)
    assert results[0].corp_name == "삼성전자"


def test_resolve_company_listed_priority_on_partial_match():
    corps = parse_corp_code_xml(SAMPLE_XML)
    results = resolve_company("삼성", corps)
    names = [c.corp_name for c in results]
    assert names[0] == "삼성전자"  # 상장사 우선


def test_resolve_company_no_match():
    corps = parse_corp_code_xml(SAMPLE_XML)
    assert resolve_company("존재하지않는회사", corps) == []


def test_tsv_roundtrip(tmp_path: Path):
    corps = parse_corp_code_xml(SAMPLE_XML)
    out = tmp_path / "corp_codes.tsv"
    write_tsv(corps, out)
    loaded = load_tsv(out)
    assert loaded == corps
