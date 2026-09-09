"""Auto-loaded step definitions for the BDD feature files.

pytest-bdd discovers this module by convention (``conftest.py`` next to the
``.feature`` files) so every Given/When/Then below is available to scenarios
in ``US01_session.feature``, ``US02_debate.feature`` and ``US03_report.feature``.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from pytest_bdd import given, parsers, then, when

from foodarena_ai import main as _main
from foodarena_ai.debate import (
    AgentArgument,
    AgentName,
    DebateController,
    DebateSession,
    MockDebateAgent,
)
from foodarena_ai.debate import (
    SessionStatus as LegacyStatus,
)
from foodarena_ai.domain import PreferenceInput, Weather
from foodarena_ai.service import DebateService

# One in-memory backend shared by all API-driven steps.
_service = DebateService(in_memory=True)


def _api_client() -> TestClient:
    def override():
        return _service

    _main.app.dependency_overrides[_main.get_service] = override
    return TestClient(_main.app)


_client = _api_client()
_sessions: dict[str, dict] = {}


def _new_prefs(**overrides) -> PreferenceInput:
    values = dict(taste="麻辣", budget_yuan=15, weather=Weather.RAINY, companions=2)
    values.update(overrides)
    return PreferenceInput.model_validate(values)


# ---------------------------------------------------------------------------
# US01: session creation
# ---------------------------------------------------------------------------


@given("校园菜单和可用的会话接口")
def campus_menu_available() -> None:
    assert _client.get("/healthz").status_code == 200


@when(
    parsers.parse(
        "用户提交合法偏好：口味「{taste}」、预算 {budget:d} 元、天气 {weather}、同行 {companions:d} 人"  # noqa: E501
    )
)
def submit_valid_prefs(taste: str, budget: int, weather: str, companions: int) -> None:
    payload = {
        "taste": taste,
        "budget_yuan": budget,
        "weather": weather,
        "companions": companions,
    }
    _sessions["last_create"] = {
        "response": _client.post("/api/v1/sessions", json=payload)
    }


@when(parsers.parse("用户提交非法偏好：空口味、预算 {budget:d} 元"))
def submit_invalid_prefs(budget: int) -> None:
    _sessions.clear()
    payload = {"taste": "", "budget_yuan": budget, "weather": "rainy", "companions": 2}
    _sessions["last_create"] = {
        "response": _client.post("/api/v1/sessions", json=payload)
    }


@then("系统返回 HTTP 201 与唯一 session_id")
def assert_201_with_id() -> None:
    response = _sessions["last_create"]["response"]
    assert response.status_code == 201
    body = response.json()
    assert len(body["session_id"]) == 36
    _sessions["current"] = body


@then("会话初始状态为 PENDING")
def assert_pending() -> None:
    assert _sessions["current"]["status"] == "PENDING"


@then("系统返回 HTTP 422 结构化校验错误")
def assert_422() -> None:
    response = _sessions["last_create"]["response"]
    assert response.status_code == 422
    assert "detail" in response.json()


@then("不创建任何会话")
def assert_no_session() -> None:
    assert "current" not in _sessions


# ---------------------------------------------------------------------------
# US02: three-round debate
# ---------------------------------------------------------------------------


@when("会话处于 RUNNING 状态并执行轮次控制器的 Mock 流程")
def run_mock_controller() -> None:
    arguments = [
        AgentArgument(argument=f"第 {round_number} 轮观点", evidence="Mock 证据")
        for round_number in (1, 2, 3)
    ]
    session = DebateSession(status=LegacyStatus.RUNNING)
    controller = DebateController(
        [
            MockDebateAgent(AgentName.SICHUAN_SPICY, arguments),
            MockDebateAgent(AgentName.CANTONESE_WELLNESS, arguments),
        ]
    )
    result = controller.run(session)
    _sessions["current"] = {
        "status": result.status.value,
        "messages": [message.model_dump() for message in result.messages],
    }


@then("两个 Agent 交替完成 3 轮共 6 条消息")
def assert_six_messages() -> None:
    messages = _sessions["current"]["messages"]
    assert len(messages) == 6
    assert [message["round"] for message in messages] == [1, 1, 2, 2, 3, 3]


@then("同一 Agent 不连续发言")
def assert_alternation() -> None:
    messages = _sessions["current"]["messages"]
    assert all(
        a["agent"] != b["agent"] for a, b in zip(messages, messages[1:], strict=False)
    )


@then("每条消息包含 round、agent、argument 与 evidence")
def assert_message_fields() -> None:
    for message in _sessions["current"]["messages"]:
        assert set(message) == {"round", "agent", "argument", "evidence"}


@then("会话状态推进到 VALIDATING")
def assert_validating() -> None:
    assert _sessions["current"]["status"] == "VALIDATING"


@when("会话已完成辩论并再次调用启动接口")
def rerun_finished_debate() -> None:
    view = _service.create_session(_new_prefs())
    _service.run_debate(view.session_id)
    final, _ = _service.run_debate(view.session_id)
    _sessions["current"] = {
        "status": final.status.value,
        "message_count": len(final.messages),
    }


@then("返回当前 SUCCESS 状态且消息数量仍为 6")
def assert_rerun_is_idempotent() -> None:
    assert _sessions["current"]["status"] == "SUCCESS"
    assert _sessions["current"]["message_count"] == 6


# ---------------------------------------------------------------------------
# US03: report
# ---------------------------------------------------------------------------


@when("三轮辩论消息完整且通过 Schema 校验并执行最终裁决")
def run_full_debate_to_report() -> None:
    view = _service.create_session(_new_prefs())
    final, _ = _service.run_debate(view.session_id)
    _sessions["current"] = {"status": final.status.value, "report": final.report}


@then("战报包含 dish、reason 与 confidence")
def assert_report_fields() -> None:
    report = _sessions["current"]["report"]
    assert report is not None
    assert report.dish and report.reason
    assert 0.0 <= report.confidence <= 1.0
    _sessions["report"] = report


@then("score_breakdown 包含 口味、预算、天气 与 辩论表现")
def assert_breakdown_keys() -> None:
    breakdown = _sessions["report"].score_breakdown
    assert set(breakdown) == {"taste", "budget", "weather", "debate"}


@then("会话进入 SUCCESS 状态")
def assert_success() -> None:
    assert _sessions["current"]["status"] == "SUCCESS"


@when("会话仍在 PENDING 状态并请求战报")
def request_report_before_debate() -> None:
    view = _service.create_session(_new_prefs(taste="清淡", budget_yuan=10))
    _sessions["report_response"] = _client.get(
        f"/api/v1/sessions/{view.session_id}/report"
    )


@then("接口返回 HTTP 409 且不包含伪造的成功战报")
def assert_409_gate() -> None:
    assert _sessions["report_response"].status_code == 409
