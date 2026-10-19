"""OpenDART 고유번호 전체자료를 받아 data/corp_codes.tsv로 캐싱한다.

거의 바뀌지 않는 정적 자료라서, API를 매번 부르지 않고 파일로 캐싱해
재사용한다 (법정동코드와 같은 패턴).

사용법:
    OPENDART_API_KEY=발급받은키 python scripts/download_corpcodes.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from corp_agent.corp_codes import parse_corp_code_xml, write_tsv  # noqa: E402
from corp_agent.dart_client import DartClient, extract_corp_code_xml  # noqa: E402

OUT_PATH = Path(__file__).resolve().parents[1] / "data" / "corp_codes.tsv"


def main() -> None:
    api_key = os.environ.get("OPENDART_API_KEY")
    if not api_key:
        sys.exit("OPENDART_API_KEY 환경변수가 필요합니다.")

    client = DartClient(api_key=api_key)
    print("고유번호 전체자료(zip) 다운로드 중...")
    zip_bytes = client.download_corp_code_zip()
    xml_bytes = extract_corp_code_xml(zip_bytes)
    corp_codes = parse_corp_code_xml(xml_bytes)
    write_tsv(corp_codes, OUT_PATH)
    listed = sum(1 for c in corp_codes if c.is_listed)
    print(f"{len(corp_codes)}개 회사 캐싱 완료 ({listed}개 상장사) → {OUT_PATH}")


if __name__ == "__main__":
    main()
