"""corp-agent CLI.

사용법:
    python -m corp_agent "삼성전자 작년 영업이익 어땠어?"

.env 파일(.env.example 참고)에 OPENDART_API_KEY / ANTHROPIC_API_KEY를
넣어두면 자동으로 로드한다.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from .agent import CorpAgent
from .corp_codes import load_tsv
from .dart_client import DartClient

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "corp_codes.tsv"


def main() -> None:
    parser = argparse.ArgumentParser(description="DART 기반 기업 재무 질의 에이전트")
    parser.add_argument("question", help="예: '카카오 최근 3년 매출 추이 보여줘'")
    parser.add_argument(
        "--show-calls", action="store_true", help="도구 호출 로그를 함께 출력"
    )
    args = parser.parse_args()

    opendart_key = os.environ.get("OPENDART_API_KEY")
    if not opendart_key:
        sys.exit("OPENDART_API_KEY 환경변수가 필요합니다 (.env.example 참고).")
    if not DATA_PATH.exists():
        sys.exit(
            f"{DATA_PATH} 가 없습니다. 먼저 `python scripts/download_corpcodes.py`를 실행하세요."
        )

    dart_client = DartClient(api_key=opendart_key)
    corp_codes = load_tsv(DATA_PATH)
    agent = CorpAgent(dart_client=dart_client, corp_codes=corp_codes)

    result = agent.ask(args.question)

    if args.show_calls:
        print("--- 도구 호출 로그 ---")
        for call in result.tool_calls:
            print(f"[{call.name}] input={call.input}")
        print("----------------------\n")

    print(result.answer)


if __name__ == "__main__":
    main()
