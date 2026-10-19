"""고정 정답셋 기반 eval 러너.

DART 공시는 한 번 등록되면 바뀌지 않는 "확정 데이터"이므로, 과거 확정
사업연도 기준으로 고정 정답셋을 만들어 정확도를 측정한다 (stat-agent와
동일한 설계 — realty-agent/air-agent처럼 매번 달라지는 데이터가 아니라서
eval이 더 단순하다).

cases.json에서 expected_amount가 비어있는(null) case는 SKIP으로 표시한다
— "출처 없이 숫자를 만들지 않는다"는 이 프로젝트의 원칙을 eval 자체에도
적용한 것으로, 검증되지 않은 숫자를 정답으로 깔아두고 돌리지 않는다.

사용법:
    OPENDART_API_KEY=발급받은키 python eval/run_eval.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

try:
    from dotenv import load_dotenv

    # 실행 위치(cwd)와 상관없이 항상 레포 루트의 .env를 읽는다.
    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

sys.path.insert(0, str(_REPO_ROOT / "src"))

from corp_agent import tools as corp_tools  # noqa: E402
from corp_agent.corp_codes import load_tsv  # noqa: E402
from corp_agent.dart_client import DartApiError, DartClient  # noqa: E402

CASES_PATH = Path(__file__).resolve().parent / "cases.json"
DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "corp_codes.tsv"


def main() -> None:
    api_key = os.environ.get("OPENDART_API_KEY")
    if not api_key:
        sys.exit("OPENDART_API_KEY 환경변수가 필요합니다.")
    if not DATA_PATH.exists():
        sys.exit("data/corp_codes.tsv가 없습니다. scripts/download_corpcodes.py를 먼저 실행하세요.")

    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    corp_codes = load_tsv(DATA_PATH)
    client = DartClient(api_key=api_key)

    passed = failed = skipped = 0
    for case in cases:
        if case.get("expected_amount") is None:
            print(f"SKIP  {case['id']} (expected_amount 미입력 — cases.json을 채우세요)")
            skipped += 1
            continue

        candidates = corp_tools.resolve_company(case["corp_name"], corp_codes, limit=1)
        if not candidates:
            print(f"FAIL  {case['id']}: 회사를 찾지 못함 ({case['corp_name']})")
            failed += 1
            continue

        try:
            result = corp_tools.get_financials(
                client, candidates[0]["corp_code"], case["bsns_year"], case["reprt_code"]
            )
        except DartApiError as e:
            print(f"FAIL  {case['id']}: DART API 오류 {e.status} {e.message}")
            failed += 1
            continue

        account = result["accounts"].get(case["account"])
        actual = account["amount"] if account else None
        if actual == case["expected_amount"]:
            print(f"PASS  {case['id']}: {actual:,}")
            passed += 1
        else:
            print(f"FAIL  {case['id']}: expected={case['expected_amount']!r} actual={actual!r}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed, {skipped} skipped (total {len(cases)})")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
