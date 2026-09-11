"""End-to-end service tests for session lifecycle and the three-round debate."""

from __future__ import annotations

from uuid import uuid4

import pytest

from foodarena_ai.domain import AgentName, SessionStatus
from foodarena_ai.service import (
    DebateProviderError,
    MockChefProvider,
    SessionNotFound,
)


def test_mock_debate_produces_six_alternating_messages_and_success(
    service,
    preferences,
) -> None:
    view = service.create_session(preferences)
    assert view.status is SessionStatus.PENDING
    assert view.messages == []

    final, events = service.run_debate(view.session_id)

    assert final.status is SessionStatus.SUCCESS
    assert len(final.messages) == 6
    rounds = [m.round for m in final.messages]
    agents = [m.agent for m in final.messages]
    assert rounds == [1, 1, 2, 2, 3, 3]
    assert agents == [AgentName.SICHUAN_SPICY, AgentName.CANTONESE_WELLNESS] * 3
    assert all(a != b for a, b in zip(agents, agents[1:], strict=False)), (
        "same agent must not speak twice in a row"
    )
    assert all(m.argument and m.evidence for m in final.messages)
    assert final.report is not None
    assert final.report.dish and final.report.reason
    assert set(final.report.score_breakdown) == {"taste", "budget", "weather", "debate"}
    assert 0.0 <= final.report.confidence <= 1.0

    events_names = [e.event for e in events]
    assert events_names[0] == "status"
    assert "round_started" in events_names
    assert "message" in events_names
    assert "report" in events_names
    assert events_names[-1] == "status"


def test_rerun_returns_current_state_without_duplicate_chain(
    service, preferences
) -> None:
    view = service.create_session(preferences)
    first, _ = service.run_debate(view.session_id)
    assert first.status is SessionStatus.SUCCESS

    again, events = service.run_debate(view.session_id)

    assert again.session_id == view.session_id
    assert again.status is SessionStatus.SUCCESS
    assert len(again.messages) == 6  # no second chain appended
    assert len(events) == 1  # only a status event for the re-entry


def test_unknown_session_raises_not_found(service) -> None:
    with pytest.raises(SessionNotFound):
        service.get_session(uuid4())
    with pytest.raises(SessionNotFound):
        service.run_debate(uuid4())


def test_report_persisted_and_readable_after_success(service, preferences) -> None:
    view = service.create_session(preferences)
    service.run_debate(view.session_id)
    stored = service.get_session(view.session_id)
    assert stored.status is SessionStatus.SUCCESS
    assert stored.report is not None
    # replay ends with the report event carrying the stored report
    events = service.replay_events(view.session_id)
    assert events[-1].event == "report"
    report_events = [e for e in events if e.event == "report"]
    assert len(report_events) == 1
    assert report_events[0].data["report"]["dish"] == stored.report.dish


def test_provider_failure_marks_session_failed_with_no_partial_report(
    service, preferences, monkeypatch
) -> None:
    """A provider error part-way through must yield FAILED and no success report."""

    class ExplodingProvider(MockChefProvider):
        def argument(self, ctx, *, session_id, request_id):
            if ctx.round_number == 2 and ctx.agent is AgentName.CANTONESE_WELLNESS:
                raise DebateProviderError("simulated model outage")
            return super().argument(ctx, session_id=session_id, request_id=request_id)

    view = service.create_session(preferences)
    # Inject the failing provider for the whole debate.
    service._build_provider = lambda provider: ExplodingProvider()  # type: ignore[method-assign]

    final, events = service.run_debate(view.session_id)

    assert final.status is SessionStatus.FAILED
    assert final.report is None
    event_names = [e.event for e in events]
    assert event_names[-1] == "status"
    # messages that had already been persisted remain, but no report event
    assert not any(e.event == "report" for e in events)
    stored = service.get_session(view.session_id)
    assert stored.status is SessionStatus.FAILED
    assert stored.failure_reason  # short redacted reason available
