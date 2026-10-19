"""Claude tool-use 에이전트 루프.

stat-agent/realty-agent/air-agent와 동일한 설계 원칙을 따른다:
- 모든 숫자 뒤에 출처(공시 접수번호, 사업연도, 연결/개별 여부)를 명시한다.
- 비교·증감률은 compute_growth(코드)로만 계산한다. 모델이 암산한 숫자는 쓰지 않는다.
- 모르면(계정 못 찾음, 공시 없음) 모른다고 말한다. 지어내지 않는다.
- 어떤 도구를 어떤 순서로 호출했는지 호출 로그를 그대로 노출한다 (ToolCallRecord).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

import anthropic

from . import tools as corp_tools
from .corp_codes import CorpCode
from .dart_client import DartApiError

KST = ZoneInfo("Asia/Seoul")
MODEL = os.environ.get("CORP_AGENT_MODEL", "claude-sonnet-4-5")


def latest_annual_bsns_year(reference_date: Optional[date] = None) -> str:
    """사업보고서는 회계연도 종료 후 약 3개월 뒤 공시된다 (12월 결산 기준
    통상 3월 말 제출 마감). 그래서 "최근 연간 실적"은 생각보다 과거일 수
    있다 — 4월 이전이면 재작년, 그 외엔 작년을 보수적인 기본값으로 쓴다.
    실제 공시 여부는 get_financials 호출 결과(013 여부)로 최종 확인해야
    한다 — 이 함수는 시스템 프롬프트에 넣을 힌트일 뿐, 보장된 값이 아니다.
    """
    today = reference_date or datetime.now(KST).date()
    return str(today.year - 2) if today.month <= 3 else str(today.year - 1)


TOOL_DEFINITIONS = [
    {
        "name": "resolve_company",
        "description": (
            "회사명으로 DART 고유번호(corp_code) 후보를 찾는다. 결과가 여러 개면 "
            "상장사를 우선으로 정렬해 반환하므로, 모호하면 사용자에게 어느 회사인지 "
            "확인하거나 가장 그럴듯한 상장사 후보를 선택했음을 밝히고 다음 단계로 진행한다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "회사명 (예: 삼성전자)"}
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_financials",
        "description": (
            "corp_code와 사업연도로 주요 재무계정(매출액/영업이익/당기순이익/자산총계/"
            "부채총계)을 조회한다. 연결재무제표(CFS)를 우선 시도하고 데이터가 없으면 "
            "개별재무제표(OFS)로 자동 폴백한다. 반환값의 rcept_no(접수번호)와 fs_div를 "
            "반드시 출처로 함께 제시한다. accounts의 값이 null이면 해당 연도 공시에서 "
            "그 계정을 찾지 못한 것이므로, 숫자를 지어내지 말고 모른다고 답한다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "corp_code": {"type": "string", "description": "8자리 DART 고유번호"},
                "bsns_year": {"type": "string", "description": "사업연도 (예: 2023)"},
                "reprt_code": {
                    "type": "string",
                    "description": "11011=사업보고서(연간, 기본값), 11012=반기, 11013=1분기, 11014=3분기",
                    "default": "11011",
                },
            },
            "required": ["corp_code", "bsns_year"],
        },
    },
    {
        "name": "compute_growth",
        "description": (
            "연도별 금액 목록을 받아 전년 대비 증감률(%)을 코드로 계산한다. 여러 연도의 "
            "매출/영업이익/순이익 추이나 증감률을 답할 때는 반드시 이 도구를 쓰고, "
            "직접 암산한 숫자를 답에 쓰지 않는다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "values": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "year": {"type": "string"},
                            "amount": {"type": "number"},
                        },
                        "required": ["year", "amount"],
                    },
                }
            },
            "required": ["values"],
        },
    },
]


@dataclass
class ToolCallRecord:
    name: str
    input: dict
    output: object


@dataclass
class AgentResult:
    answer: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)


def _system_prompt() -> str:
    today = datetime.now(KST).date()
    hint_year = latest_annual_bsns_year(today)
    return f"""당신은 DART(전자공시시스템) 공식 데이터만 근거로 기업 재무 질문에 답하는 에이전트입니다.

오늘(KST): {today.isoformat()}. 공시 시차 때문에 "최근 사업연도"로 보수적으로 추정한 기본값은 {hint_year}년이지만, 실제로 공시됐는지는 get_financials 호출 결과로 확인하세요 (데이터가 없으면 더 과거 연도로 재시도하세요).

규칙:
1. 모든 금액·수치 답변에는 출처(보고서 종류, 사업연도, 연결/개별 여부, 접수번호)를 함께 명시한다.
2. 연도 간 비교나 증감률은 반드시 compute_growth 도구로 계산한 값만 쓴다. 직접 암산하지 않는다.
3. get_financials의 accounts 값이 null이면 그 계정을 찾지 못한 것이다. 숫자를 지어내지 말고 "해당 연도 공시에서 OO 계정을 찾지 못했습니다"라고 답한다.
4. 회사명이 모호하면(동명 계열사 등) resolve_company 결과 중 어느 회사인지 먼저 명확히 하거나, 가장 가능성 높은 상장사 후보를 선택했음을 밝힌다.
5. 답변 마지막 줄에 "출처: ..."를 덧붙인다.
"""


class CorpAgent:
    def __init__(
        self,
        dart_client,
        corp_codes: list[CorpCode],
        client: Optional[anthropic.Anthropic] = None,
    ):
        self.dart_client = dart_client
        self.corp_codes = corp_codes
        self.client = client or anthropic.Anthropic()

    def _dispatch(self, name: str, tool_input: dict):
        if name == "resolve_company":
            return corp_tools.resolve_company(tool_input["name"], self.corp_codes)
        if name == "get_financials":
            try:
                return corp_tools.get_financials(
                    self.dart_client,
                    tool_input["corp_code"],
                    tool_input["bsns_year"],
                    tool_input.get("reprt_code", "11011"),
                )
            except DartApiError as e:
                return {"error": str(e), "status": e.status}
        if name == "compute_growth":
            return corp_tools.compute_growth(tool_input["values"])
        raise ValueError(f"알 수 없는 도구: {name}")

    def ask(self, question: str, max_turns: int = 8) -> AgentResult:
        messages: list[dict] = [{"role": "user", "content": question}]
        calls: list[ToolCallRecord] = []

        for _ in range(max_turns):
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=2000,
                system=_system_prompt(),
                tools=TOOL_DEFINITIONS,
                messages=messages,
            )

            if response.stop_reason != "tool_use":
                text = "".join(b.text for b in response.content if b.type == "text")
                return AgentResult(answer=text, tool_calls=calls)

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                output = self._dispatch(block.name, block.input)
                calls.append(ToolCallRecord(name=block.name, input=block.input, output=output))
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(output, ensure_ascii=False, default=str),
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        return AgentResult(
            answer="(최대 턴 수를 초과했습니다. 질문을 더 구체화해 주세요.)", tool_calls=calls
        )
