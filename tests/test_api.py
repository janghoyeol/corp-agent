from fastapi.testclient import TestClient

from corp_agent.agent import AgentResult, ToolCallRecord
from corp_agent.api import create_app


class DummyAgent:
    """실제 API 키 없이 라우팅/직렬화 로직만 검증하기 위한 가짜 에이전트."""

    def __init__(self, result: AgentResult):
        self._result = result

    def ask(self, question, max_turns=8):
        return self._result


def _result_with_chart():
    return AgentResult(
        answer="테스트 답변입니다.\n출처: 테스트 사업보고서 (접수번호: 12345)",
        tool_calls=[
            ToolCallRecord(
                name="resolve_company",
                input={"name": "삼성전자"},
                output=[
                    {
                        "corp_code": "00126380",
                        "corp_name": "삼성전자",
                        "stock_code": "005930",
                        "is_listed": True,
                    }
                ],
            ),
            ToolCallRecord(
                name="compute_growth",
                input={
                    "values": [
                        {"year": "2022", "amount": 100},
                        {"year": "2023", "amount": 120},
                    ]
                },
                output=[
                    {"year": "2022", "amount": 100, "yoy_growth_pct": None},
                    {"year": "2023", "amount": 120, "yoy_growth_pct": 20.0},
                ],
            ),
        ],
    )


def test_ask_returns_answer_company_and_chart():
    app = create_app(agent=DummyAgent(_result_with_chart()))
    client = TestClient(app)

    resp = client.post("/api/ask", json={"question": "삼성전자 매출 추이 보여줘"})

    assert resp.status_code == 200
    body = resp.json()
    assert "테스트 답변" in body["answer"]
    assert body["company_name"] == "삼성전자"
    assert len(body["chart"]) == 2
    assert body["chart"][1]["yoy_growth_pct"] == 20.0
    assert body["tool_calls"][0]["name"] == "resolve_company"


def test_ask_without_compute_growth_has_no_chart():
    result = AgentResult(
        answer="단일 연도 답변. 출처: 테스트",
        tool_calls=[
            ToolCallRecord(name="resolve_company", input={"name": "카카오"}, output=[]),
        ],
    )
    app = create_app(agent=DummyAgent(result))
    client = TestClient(app)

    resp = client.post("/api/ask", json={"question": "카카오 매출 알려줘"})

    assert resp.status_code == 200
    assert resp.json()["chart"] is None


def test_ask_rejects_empty_question():
    app = create_app(agent=DummyAgent(AgentResult(answer="", tool_calls=[])))
    client = TestClient(app)

    resp = client.post("/api/ask", json={"question": "   "})

    assert resp.status_code == 400


def test_ask_rejects_overly_long_question():
    app = create_app(agent=DummyAgent(AgentResult(answer="", tool_calls=[])))
    client = TestClient(app)

    resp = client.post("/api/ask", json={"question": "가" * 201})

    assert resp.status_code == 400


def test_rate_limit_blocks_after_threshold(monkeypatch):
    monkeypatch.setenv("CORP_AGENT_RATE_LIMIT_PER_10MIN", "3")
    app = create_app(agent=DummyAgent(_result_with_chart()))
    client = TestClient(app)

    for _ in range(3):
        resp = client.post("/api/ask", json={"question": "삼성전자"})
        assert resp.status_code == 200

    blocked = client.post("/api/ask", json={"question": "삼성전자"})
    assert blocked.status_code == 429


def test_ask_without_agent_or_env_key_returns_500():
    import os

    os.environ.pop("OPENDART_API_KEY", None)  # CI 환경엔 애초에 설정돼 있지 않음

    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.post("/api/ask", json={"question": "삼성전자"})

    assert resp.status_code == 500
