"""Three-round, dual-agent debate orchestration."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class SessionStatus(StrEnum):
    """Lifecycle states shared by debate sessions."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    VALIDATING = "VALIDATING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class AgentName(StrEnum):
    """Stable identifiers for the two FoodArena debate agents."""

    SICHUAN_SPICY = "sichuan_spicy"
    CANTONESE_WELLNESS = "cantonese_wellness"


class AgentArgument(BaseModel):
    """Structured content produced for one debate turn."""

    model_config = ConfigDict(frozen=True)

    argument: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class AgentMessage(AgentArgument):
    """A validated message recorded in a debate session."""

    round: int = Field(ge=1, le=3)
    agent: AgentName


class DebateSession(BaseModel):
    """Minimal session contract needed by the round controller."""

    model_config = ConfigDict(validate_assignment=True)

    session_id: UUID = Field(default_factory=uuid4)
    status: SessionStatus = SessionStatus.PENDING
    messages: list[AgentMessage] = Field(default_factory=list)


class DebateAgent(Protocol):
    """Provider-neutral interface implemented by real and Mock agents."""

    @property
    def name(self) -> AgentName: ...

    def respond(
        self,
        *,
        round_number: int,
        history: Sequence[AgentMessage],
    ) -> AgentArgument: ...


class DebateControllerError(Exception):
    """Raised when a debate cannot be run under the controller contract."""


class MockDebateAgent:
    """Deterministic agent for demos and tests without model access."""

    def __init__(self, name: AgentName, arguments: Sequence[AgentArgument]) -> None:
        if len(arguments) != 3:
            raise ValueError("a Mock agent requires exactly three arguments")
        self._name = name
        self._arguments = tuple(arguments)

    @property
    def name(self) -> AgentName:
        return self._name

    def respond(
        self,
        *,
        round_number: int,
        history: Sequence[AgentMessage],
    ) -> AgentArgument:
        del history
        return self._arguments[round_number - 1]


class DebateController:
    """Run two distinct agents in a fixed order for exactly three rounds."""

    ROUNDS = 3

    def __init__(self, agents: Sequence[DebateAgent]) -> None:
        if len(agents) != 2:
            raise ValueError("the debate controller requires exactly two agents")
        if agents[0].name == agents[1].name:
            raise ValueError("the debate controller requires two distinct agents")
        self._agents = tuple(agents)

    def run(self, session: DebateSession) -> DebateSession:
        """Complete the debate and atomically advance the supplied session."""
        if session.status is not SessionStatus.RUNNING:
            raise DebateControllerError("session must be RUNNING to start a debate")
        if session.messages:
            raise DebateControllerError("session must not contain existing messages")

        messages: list[AgentMessage] = []
        for round_number in range(1, self.ROUNDS + 1):
            for agent in self._agents:
                content = agent.respond(
                    round_number=round_number,
                    history=tuple(messages),
                )
                messages.append(
                    AgentMessage(
                        round=round_number,
                        agent=agent.name,
                        argument=content.argument,
                        evidence=content.evidence,
                    )
                )

        session.messages = messages
        session.status = SessionStatus.VALIDATING
        return session
