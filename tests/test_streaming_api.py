from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _parse_sse_events(text: str):
    normalized = text.replace("\r\n", "\n")
    events = []
    for block in normalized.split("\n\n"):
        lines = [line for line in block.split("\n") if line]
        if not lines:
            continue
        event_name = "message"
        data = ""
        for line in lines:
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].strip()
        events.append((event_name, data))
    return events


class _FakeSession:
    def __init__(self, conversation_id: str = "conv-test"):
        self.metadata = SimpleNamespace(
            conversation_id=conversation_id,
            user_id="web_user",
            agent_id="",
            context_strategy="FULL_CONTEXT",
        )

    def get_openai_format(self):
        return []


class _FakeSessionContext:
    def __init__(self, session=None):
        self.session = session or _FakeSession()
        self.messages = []
        self.saved = False
        self.absorbed = None

    def load_session(self, conversation_id: str):
        self.session.metadata.conversation_id = conversation_id

    def get_session(self):
        return self.session

    def create_session(self, user_id: str, agent_id: str):
        self.session = _FakeSession()
        self.session.metadata.user_id = user_id
        self.session.metadata.agent_id = agent_id

    def add_message(self, role: str, content: str):
        self.messages.append((role, content))

    def absorb_graph_result(self, final_state):
        self.absorbed = final_state

    def save(self, force: bool = False):
        self.saved = force


def test_bazi_analyze_stream_emits_progress_and_result(monkeypatch):
    from src.api import bazi_api

    fake_ctx = _FakeSessionContext()

    class FakeGraphApp:
        async def astream(self, initial_state, stream_mode="updates"):
            yield {"validate_input": {"status": "input_validated"}}
            yield {"calculate_bazi": {"status": "calculation_completed"}}
            yield {
                "safety_check": {
                    "safe_output": {
                        "message": "分析完成",
                        "data": {
                            "llm_analysis": "命局清晰。后运平稳。",
                            "basic_data": {},
                            "message": "分析完成",
                        },
                        "blocked": False,
                    },
                    "status": "safety_checked",
                }
            }

    monkeypatch.setattr(bazi_api, "get_session_context", lambda: fake_ctx)
    monkeypatch.setattr(bazi_api, "simple_app", FakeGraphApp())
    monkeypatch.setattr(bazi_api, "bazi_app", FakeGraphApp())

    app = FastAPI()
    app.include_router(bazi_api.router)
    client = TestClient(app)

    with client.stream(
        "POST",
        "/api/v1/bazi/analyze/stream",
        json={
            "year": 1990,
            "month": 5,
            "day": 15,
            "hour": 10,
            "gender": "男",
            "analysis_mode": "simple",
        },
    ) as response:
        body = "".join(response.iter_text())

    events = _parse_sse_events(body)
    event_names = [name for name, _ in events]

    assert response.status_code == 200
    assert "meta" in event_names
    assert "progress" in event_names
    assert "partial" in event_names
    assert "result" in event_names
    assert "done" in event_names
    assert "命局清晰" in body


def test_bazi_followup_stream_emits_chunked_safe_reply(monkeypatch):
    from src.api import bazi_api

    fake_ctx = _FakeSessionContext()

    class FakeAgent:
        async def handle_followup(self, session, query: str) -> str:
            return "这是追问回复。这里还有补充说明。"

    monkeypatch.setattr(bazi_api, "get_session_context", lambda: fake_ctx)
    monkeypatch.setattr(bazi_api, "BaziAgent", FakeAgent)

    app = FastAPI()
    app.include_router(bazi_api.router)
    client = TestClient(app)

    with client.stream(
        "POST",
        "/api/v1/bazi/followup/stream",
        json={"conversation_id": "conv-test", "query": "再详细说说"},
    ) as response:
        body = "".join(response.iter_text())

    events = _parse_sse_events(body)
    event_names = [name for name, _ in events]

    assert response.status_code == 200
    assert event_names.count("partial") >= 1
    assert "result" in event_names
    assert "done" in event_names
    assert "补充说明" in body
    assert fake_ctx.saved is True


def test_tarot_analyze_stream_emits_progress_and_result(monkeypatch):
    from src.api import tarot_api

    fake_ctx = _FakeSessionContext()

    class FakeTarotGraph:
        async def astream(self, initial_state, stream_mode="updates"):
            yield {"tool_node": {"spread_info": {"name_cn": "三张牌阵"}, "executor_state": {}}}
            yield {
                "tool_node": {
                    "drawn_cards": [{"card_name_cn": "太阳"}],
                    "executor_state": {"card_interpretations": ["向上发展"]},
                }
            }
            yield {
                "agent_node": {"llm_response": "整体趋势积极，建议主动把握机会。"}
            }
            yield {
                "safety_node": {
                    "tarot_result": {
                        "spread": {"name_cn": "三张牌阵"},
                        "drawn_cards": [{"card_name_cn": "太阳"}],
                        "synthesis": "整体趋势积极，建议主动把握机会。",
                    },
                    "safe_output": {
                        "spread": {"name_cn": "三张牌阵"},
                        "drawn_cards": [{"card_name_cn": "太阳"}],
                        "synthesis": "整体趋势积极，建议主动把握机会。",
                    },
                    "llm_response": "整体趋势积极，建议主动把握机会。",
                    "status": "completed",
                }
            }

    monkeypatch.setattr(tarot_api, "get_session_context", lambda: fake_ctx)
    monkeypatch.setattr(tarot_api, "tarot_app", FakeTarotGraph())

    app = FastAPI()
    app.include_router(tarot_api.router)
    client = TestClient(app)

    with client.stream(
        "POST",
        "/api/v1/tarot/analyze/stream",
        json={"question": "我最近的事业怎么样？", "question_type": "事业"},
    ) as response:
        body = "".join(response.iter_text())

    events = _parse_sse_events(body)
    event_names = [name for name, _ in events]

    assert response.status_code == 200
    assert event_names.count("progress") >= 3
    assert "partial" in event_names
    assert "result" in event_names
    assert "主动把握机会" in body
