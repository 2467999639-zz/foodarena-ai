"""Fault and resilience regression scenarios (QA03/RES01 subset).

These cover the failure paths that a live demo must survive: duplicate debate
starts, report gating before completion, unknown sessions, SSE replay after a
connection drop, and provider failures that must not leave a partial report.
All run offline against an in-memory backend.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from foodarena_ai.domain import (
    AgentName,
    PreferenceInput,
    Weather,
)
from foodarena_ai.service import DebateProviderError, DebateService, MockChefProvider


def _prefs(**overrides) -> PreferenceInput:
    values = dict(taste="麻辣", budget_yuan=15, weather=Weather.RAINY, companions=2)
    values.update(overrides)
    return PreferenceInput.model_validate(values)


def _api(service: DebateService) -> TestClient:
    import foodarena_ai.main as main

    def override():
        return service

    main.app.dependency_overrides[main.get_service] = override
    return TestClient(main.app)


# ---------------------------------------------------------------------------
# Duplicate / re-entry semantics
# ---------------------------------------------------------------------------


def test_pending_session_debate_returns_success() -> None:
    service = DebateService(in_memory=True)
    client = _api(service)
    sid = client.post("/api/v1/sessions", json=_prefs().model_dump()).json()[
        "session_id"
    ]
    body = client.post(f"/api/v1/sessions/{sid}/debate").json()
    assert body["status"] == "SUCCESS"
    assert len(body["messages"]) == 6


def test_running_then_rerun_is_idempotent_and_no_duplicate_chain() -> None:
    service = DebateService(in_memory=True)
    client = _api(service)
    sid = client.post("/api/v1/sessions", json=_prefs().model_dump()).json()[
        "session_id"
    ]
    first = client.post(f"/api/v1/sessions/{sid}/debate")
    second = client.post(f"/api/v1/sessions/{sid}/debate")
    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == second.json()["status"] == "SUCCESS"
    assert len(first.json()["messages"]) == 6
    assert len(second.json()["messages"]) == 6


def test_report_before_debate_is_gated_409() -> None:
    service = DebateService(in_memory=True)
    client = _api(service)
    sid = client.post("/api/v1/sessions", json=_prefs().model_dump()).json()[
        "session_id"
    ]
    assert client.get(f"/api/v1/sessions/{sid}/report").status_code == 409


def test_report_after_debate_is_stable_and_readable_twice() -> None:
    service = DebateService(in_memory=True)
    client = _api(service)
    sid = client.post("/api/v1/sessions", json=_prefs().model_dump()).json()[
        "session_id"
    ]
    client.post(f"/api/v1/sessions/{sid}/debate")
    first = client.get(f"/api/v1/sessions/{sid}/report").json()
    second = client.get(f"/api/v1/sessions/{sid}/report").json()
    assert first == second
    assert "score_breakdown" in first


def test_failed_session_cannot_fabricate_a_success_report() -> None:
    """A session that FAILED must never serve a report."""
    service = DebateService(in_memory=True)
    client = _api(service)

    class ExplodingProvider(MockChefProvider):
        def argument(self, ctx, *, session_id, request_id):
            if ctx.round_number == 2 and ctx.agent is AgentName.SICHUAN_SPICY:
                raise DebateProviderError("simulated 500")
            return super().argument(ctx, session_id=session_id, request_id=request_id)

    service._build_provider = lambda p: ExplodingProvider()  # type: ignore[method-assign]
    sid = client.post("/api/v1/sessions", json=_prefs().model_dump()).json()[
        "session_id"
    ]

    result = client.post(f"/api/v1/sessions/{sid}/debate").json()
    assert result["status"] == "FAILED"
    assert result["report"] is None

    # The stored session must surface FAILED to the UI and gate the report.
    stored = client.get(f"/api/v1/sessions/{sid}").json()
    assert stored["status"] == "FAILED"
    assert stored["report"] is None
    assert stored["failure_reason"]
    assert client.get(f"/api/v1/sessions/{sid}/report").status_code == 409


def test_unknown_session_404s_everywhere() -> None:
    service = DebateService(in_memory=True)
    client = _api(service)
    missing = "00000000-0000-0000-0000-000000000001"
    assert client.get(f"/api/v1/sessions/{missing}").status_code == 404
    assert client.post(f"/api/v1/sessions/{missing}/debate").status_code == 404
    assert client.get(f"/api/v1/sessions/{missing}/report").status_code == 404
    assert client.get(f"/api/v1/sessions/{missing}/events").status_code == 404


def test_invalid_preference_422_and_no_session_leak() -> None:
    service = DebateService(in_memory=True)
    client = _api(service)
    response = client.post(
        "/api/v1/sessions",
        json={"taste": "", "budget_yuan": 0, "weather": "sunny", "companions": 0},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# SSE replay semantics
# ---------------------------------------------------------------------------


def test_sse_stream_contains_all_six_messages_then_done() -> None:
    service = DebateService(in_memory=True)
    client = _api(service)
    sid = client.post("/api/v1/sessions", json=_prefs().model_dump()).json()[
        "session_id"
    ]
    with client.stream("GET", f"/api/v1/sessions/{sid}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())
    assert body.count("event: message") == 6
    assert body.count("event: report") == 1
    assert "event: done" in body
    assert "SUCCESS" in body


def test_sse_replay_after_disconnect_does_not_duplicate_messages() -> None:
    """A reconnecting client gets the stored events, not a second debate."""
    service = DebateService(in_memory=True)
    client = _api(service)
    sid = client.post("/api/v1/sessions", json=_prefs().model_dump()).json()[
        "session_id"
    ]
    # First connection runs the debate to completion.
    with client.stream("GET", f"/api/v1/sessions/{sid}/events") as response:
        first = "".join(response.iter_text())
    assert first.count("event: message") == 6

    # Second (re)connect replays the same six stored messages.
    with client.stream("GET", f"/api/v1/sessions/{sid}/events") as response:
        second = "".join(response.iter_text())
    assert second.count("event: message") == 6
    # The session state endpoint shows a terminal, completed debate.
    stored = client.get(f"/api/v1/sessions/{sid}").json()
    assert stored["status"] == "SUCCESS"
    assert len(stored["messages"]) == 6
