from __future__ import annotations

from collections.abc import Sequence

import pytest

from foodarena_ai.debate import (
    AgentArgument,
    AgentMessage,
    AgentName,
    DebateController,
    DebateControllerError,
    DebateSession,
    MockDebateAgent,
    SessionStatus,
)


def arguments(agent_label: str) -> list[AgentArgument]:
    return [
        AgentArgument(
            argument=f"{agent_label} argument for round {round_number}",
            evidence=f"{agent_label} evidence for round {round_number}",
        )
        for round_number in range(1, 4)
    ]


def mock_agents() -> tuple[MockDebateAgent, MockDebateAgent]:
    return (
        MockDebateAgent(AgentName.SICHUAN_SPICY, arguments("spicy")),
        MockDebateAgent(AgentName.CANTONESE_WELLNESS, arguments("wellness")),
    )


def test_mock_flow_produces_six_alternating_messages_across_three_rounds() -> None:
    session = DebateSession(status=SessionStatus.RUNNING)

    result = DebateController(mock_agents()).run(session)

    assert result is session
    assert result.status is SessionStatus.VALIDATING
    assert len(result.messages) == 6
    assert [message.round for message in result.messages] == [1, 1, 2, 2, 3, 3]
    assert [message.agent for message in result.messages] == [
        AgentName.SICHUAN_SPICY,
        AgentName.CANTONESE_WELLNESS,
    ] * 3
    assert all(
        current.agent != following.agent
        for current, following in zip(
            result.messages, result.messages[1:], strict=False
        )
    )
    assert all(message.argument and message.evidence for message in result.messages)
    assert set(result.messages[0].model_dump()) == {
        "round",
        "agent",
        "argument",
        "evidence",
    }


@pytest.mark.parametrize(
    "status",
    [
        SessionStatus.PENDING,
        SessionStatus.VALIDATING,
        SessionStatus.SUCCESS,
        SessionStatus.FAILED,
    ],
)
def test_controller_rejects_sessions_that_are_not_running(
    status: SessionStatus,
) -> None:
    session = DebateSession(status=status)

    with pytest.raises(DebateControllerError, match="must be RUNNING"):
        DebateController(mock_agents()).run(session)

    assert session.status is status
    assert session.messages == []


def test_controller_rejects_existing_messages() -> None:
    existing = AgentMessage(
        round=1,
        agent=AgentName.SICHUAN_SPICY,
        argument="existing argument",
        evidence="existing evidence",
    )
    session = DebateSession(status=SessionStatus.RUNNING, messages=[existing])

    with pytest.raises(DebateControllerError, match="existing messages"):
        DebateController(mock_agents()).run(session)

    assert session.messages == [existing]
    assert session.status is SessionStatus.RUNNING


def test_controller_requires_two_distinct_agents() -> None:
    spicy = MockDebateAgent(AgentName.SICHUAN_SPICY, arguments("spicy"))

    with pytest.raises(ValueError, match="exactly two"):
        DebateController([spicy])
    with pytest.raises(ValueError, match="distinct"):
        DebateController([spicy, spicy])


def test_mock_agent_requires_exactly_three_arguments() -> None:
    with pytest.raises(ValueError, match="exactly three"):
        MockDebateAgent(AgentName.SICHUAN_SPICY, arguments("spicy")[:2])


def test_agent_failure_leaves_session_unchanged() -> None:
    class FailingAgent:
        name = AgentName.CANTONESE_WELLNESS

        def respond(
            self,
            *,
            round_number: int,
            history: Sequence[AgentMessage],
        ) -> AgentArgument:
            del round_number, history
            raise RuntimeError("Mock generation failed")

    session = DebateSession(status=SessionStatus.RUNNING)
    spicy = MockDebateAgent(AgentName.SICHUAN_SPICY, arguments("spicy"))

    with pytest.raises(RuntimeError, match="Mock generation failed"):
        DebateController([spicy, FailingAgent()]).run(session)

    assert session.status is SessionStatus.RUNNING
    assert session.messages == []
