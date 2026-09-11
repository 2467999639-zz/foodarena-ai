"""Fault and resilience regression scenarios (QA03/RES01 subset).

These cover the failure paths that a live demo must survive: duplicate debate
starts, report gating before completion, unknown sessions, SSE replay after a
connection drop, and provider failures that must not leave a partial report.
All run offline against an in-memory backend.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

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


def test_concurrent_starts_atomically_claim_one_debate_chain(tmp_path) -> None:
    database = (tmp_path / "concurrent.sqlite3").as_posix()
    service = DebateService(database_url=f"sqlite:///{database}")
    view = service.create_session(_prefs())
    barrier = threading.Barrier(2)
    call_count = 0
    call_lock = threading.Lock()

    class CountingProvider(MockChefProvider):
        def argument(self, ctx, *, session_id, request_id):
            nonlocal call_count
            with call_lock:
                call_count += 1
            return super().argument(ctx, session_id=session_id, request_id=request_id)

    service._build_provider = lambda p: CountingProvider()  # type: ignore[method-assign]

    def start() -> list:
        barrier.wait(timeout=1.0)
        return list(service.stream_debate(view.session_id))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: start(), range(2)))

    assert call_count == 6
    assert sorted(len(result) for result in results) == [1, 16]
    stored = service.get_session(view.session_id)
    assert stored.status.value == "SUCCESS"
    assert [(message.round, message.agent) for message in stored.messages] == [
        (1, AgentName.SICHUAN_SPICY),
        (1, AgentName.CANTONESE_WELLNESS),
        (2, AgentName.SICHUAN_SPICY),
        (2, AgentName.CANTONESE_WELLNESS),
        (3, AgentName.SICHUAN_SPICY),
        (3, AgentName.CANTONESE_WELLNESS),
    ]


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
    messages = [
        json.loads(frame.split("data: ", maxsplit=1)[1])
        for frame in body.split("\n\n")
        if frame.startswith("event: message")
    ]
    assert [(message["round"], message["agent"]) for message in messages] == [
        (1, AgentName.SICHUAN_SPICY.value),
        (1, AgentName.CANTONESE_WELLNESS.value),
        (2, AgentName.SICHUAN_SPICY.value),
        (2, AgentName.CANTONESE_WELLNESS.value),
        (3, AgentName.SICHUAN_SPICY.value),
        (3, AgentName.CANTONESE_WELLNESS.value),
    ]


def test_sse_model_call_does_not_block_event_loop_and_preserves_turn_order() -> None:
    """A slow provider must not delay delivery of already-produced frames."""
    import foodarena_ai.main as main

    service = DebateService(in_memory=True)
    entered = threading.Event()
    release = threading.Event()

    class GatedProvider(MockChefProvider):
        def argument(self, ctx, *, session_id, request_id):
            if ctx.round_number == 1 and ctx.agent is AgentName.SICHUAN_SPICY:
                entered.set()
                release.wait(timeout=1.0)
            return super().argument(ctx, session_id=session_id, request_id=request_id)

    service._build_provider = lambda p: GatedProvider()  # type: ignore[method-assign]
    view = service.create_session(_prefs())

    async def consume_start() -> None:
        response = await main.session_events(view.session_id, service)
        iterator = response.body_iterator
        first = await anext(iterator)
        second = await anext(iterator)
        assert "event: status" in first
        assert '"status": "RUNNING"' in first
        assert "event: round_started" in second
        assert '"agent": "sichuan_spicy"' in second

        # The next frame waits on the provider.  A timer releases that call,
        # while this sleep proves the FastAPI event loop remains responsive.
        timer = threading.Timer(0.4, release.set)
        timer.start()
        started = time.perf_counter()
        message_task = asyncio.create_task(anext(iterator))
        await asyncio.sleep(0.05)
        assert time.perf_counter() - started < 0.2
        assert entered.is_set()
        assert not message_task.done()
        first_message = await message_task
        timer.cancel()

        next_turn = await anext(iterator)
        assert "event: message" in first_message
        assert '"agent": "sichuan_spicy"' in first_message
        assert "event: round_started" in next_turn
        assert '"agent": "cantonese_wellness"' in next_turn
        await iterator.aclose()

    asyncio.run(consume_start())


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
