"""corp-agent 웹 API + 정적 프런트엔드 서빙.

CLI(cli.py)와 같은 CorpAgent를 그대로 재사용한다 — 로직은 한 곳에만 있고,
이 모듈은 그 위에 얇은 FastAPI 레이어만 얹는다.

로컬 실행:
    uvicorn corp_agent.api:app --reload --port 8000
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agent import AgentResult, CorpAgent
from .corp_codes import load_tsv
from .dart_client import DartClient

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WEB_DIR = _REPO_ROOT / "web"
_DATA_PATH = _REPO_ROOT / "data" / "corp_codes.tsv"

try:
    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass


class AskRequest(BaseModel):
    question: str


class ToolCallOut(BaseModel):
    name: str
    input: dict
    output: Any


class ChartPoint(BaseModel):
    year: str
    amount: Optional[float] = None
    yoy_growth_pct: Optional[float] = None


class AskResponse(BaseModel):
    answer: str
    tool_calls: list[ToolCallOut]
    chart: Optional[list[ChartPoint]] = None
    company_name: Optional[str] = None


def _extract_chart(result: AgentResult) -> Optional[list[ChartPoint]]:
    """가장 마지막 compute_growth 호출 결과를 차트 데이터로 쓴다.

    compute_growth는 모델 암산이 아니라 코드로 계산된 값이므로, 화면에
    그대로 그려도 되는 "신뢰 가능한" 숫자다.
    """
    for call in reversed(result.tool_calls):
        if call.name == "compute_growth" and isinstance(call.output, list):
            try:
                return [ChartPoint(**point) for point in call.output]
            except (TypeError, ValueError):
                return None
    return None


def _extract_company_name(result: AgentResult) -> Optional[str]:
    for call in result.tool_calls:
        if call.name == "resolve_company" and isinstance(call.output, list) and call.output:
            return call.output[0].get("corp_name")
    return None


def create_app(agent: Optional[CorpAgent] = None) -> FastAPI:
    """agent를 주입할 수 있게 해서, 테스트에서 실제 API 키 없이 더미
    에이전트로 라우팅/직렬화 로직만 검증할 수 있게 한다."""
    app = FastAPI(title="corp-agent")
    state: dict[str, Any] = {"agent": agent}

    def get_agent() -> CorpAgent:
        if state["agent"] is None:
            api_key = os.environ.get("OPENDART_API_KEY")
            if not api_key:
                raise HTTPException(500, "OPENDART_API_KEY가 서버에 설정되어 있지 않습니다.")
            if not _DATA_PATH.exists():
                raise HTTPException(
                    500,
                    "data/corp_codes.tsv가 없습니다. scripts/download_corpcodes.py를 먼저 실행하세요.",
                )
            dart_client = DartClient(api_key=api_key)
            corp_codes = load_tsv(_DATA_PATH)
            state["agent"] = CorpAgent(dart_client=dart_client, corp_codes=corp_codes)
        return state["agent"]

    @app.post("/api/ask", response_model=AskResponse)
    def ask(req: AskRequest) -> AskResponse:
        question = req.question.strip()
        if not question:
            raise HTTPException(400, "질문을 입력해주세요.")
        result = get_agent().ask(question)
        return AskResponse(
            answer=result.answer,
            tool_calls=[
                ToolCallOut(name=c.name, input=c.input, output=c.output)
                for c in result.tool_calls
            ],
            chart=_extract_chart(result),
            company_name=_extract_company_name(result),
        )

    if _WEB_DIR.exists():
        app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")

    return app


app = create_app()
