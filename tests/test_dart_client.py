import io
import json
import zipfile
from unittest.mock import MagicMock

import pytest

from corp_agent.dart_client import (
    DartAuthError,
    DartClient,
    DartNoDataError,
    DartRateLimitError,
    extract_corp_code_xml,
)


def _mock_session(json_payload=None, content=None):
    session = MagicMock()
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    if json_payload is not None:
        resp.json.return_value = json_payload
    if content is not None:
        resp.content = content
    session.get.return_value = resp
    return session


def test_get_financials_ok():
    payload = {
        "status": "000",
        "message": "정상",
        "list": [{"account_nm": "매출액", "thstrm_amount": "1,000"}],
    }
    client = DartClient(api_key="k", session=_mock_session(json_payload=payload))
    rows = client.get_financials("00126380", "2023")
    assert rows[0]["account_nm"] == "매출액"


def test_get_financials_no_data_raises():
    payload = {"status": "013", "message": "조회된 데이타가 없습니다."}
    client = DartClient(api_key="k", session=_mock_session(json_payload=payload))
    with pytest.raises(DartNoDataError):
        client.get_financials("00126380", "2023", fs_div="CFS")


def test_get_financials_auth_error():
    payload = {"status": "011", "message": "사용할 수 없는 키입니다."}
    client = DartClient(api_key="bad", session=_mock_session(json_payload=payload))
    with pytest.raises(DartAuthError):
        client.get_financials("00126380", "2023")


def test_get_financials_rate_limit():
    payload = {"status": "020", "message": "요청 제한을 초과하였습니다."}
    client = DartClient(api_key="k", session=_mock_session(json_payload=payload))
    with pytest.raises(DartRateLimitError):
        client.get_financials("00126380", "2023")


def test_download_corp_code_zip_rejects_non_zip_error_payload():
    payload = {"status": "011", "message": "사용할 수 없는 키입니다."}
    session = _mock_session(content=json.dumps(payload).encode("utf-8"))
    client = DartClient(api_key="bad", session=session)
    with pytest.raises(DartAuthError):
        client.download_corp_code_zip()


def test_download_corp_code_zip_returns_bytes_for_valid_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CORPCODE.xml", b"<result></result>")
    session = _mock_session(content=buf.getvalue())
    client = DartClient(api_key="k", session=session)
    assert client.download_corp_code_zip().startswith(b"PK")


def test_extract_corp_code_xml_roundtrip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CORPCODE.xml", b"<result><list></list></result>")
    xml_bytes = extract_corp_code_xml(buf.getvalue())
    assert b"<result>" in xml_bytes


def test_api_key_required():
    with pytest.raises(ValueError):
        DartClient(api_key="")
