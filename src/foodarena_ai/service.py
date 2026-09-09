"""Debate orchestration: create sessions, run three rounds, judge the result.

Lifecycle owned here: ``PENDING -> RUNNING -> VALIDATING -> SUCCESS`` (or
``FAILED`` on any provider/schema failure). Messages and the final report are
persisted transactionally and an ordered event list is returned so the SSE
endpoint can stream live and replay from storage afterwards.

Concurrency note
----------------
The backend runs as a single uvicorn worker against one SQLite file, and the
debate endpoint is synchronous, so at most one debate mutates a row at a time.
A re-entry attempt on an already-started session simply returns the stored
state instead of spawning a second chain.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from . import prompts
from .db import (
    MessageRow,
    PreferenceRow,
    RecommendationRow,
    SessionRow,
    create_all,
    make_engine,
    row_to_domain,
    utc_now,
)
from .domain import (
    AgentMessage,
    AgentName,
    DebateReport,
    PreferenceInput,
    ProviderMode,
    SessionStatus,
    SessionView,
    Weather,
)
from .reasoning import MockReasoner
from .security import bind_request_id, redact_secrets, sanitise_user_text

LOGGER = logging.getLogger(__name__)

ROUNDS = 3
_MAX_TEXT_LEN = 200


class DebateProviderError(Exception):
    """A provider call could not produce a usable result."""


class SchemaRepairError(DebateProviderError):
    """The model output failed schema validation after repair attempts."""


class SessionNotFound(LookupError):
    """Raised when no session exists for the given id."""

    def __init__(self, session_id: UUID) -> None:
        self.session_id = session_id
        super().__init__(f"session not found: {session_id}")


# --------------------------------------------------------------------------
# Debate context & provider interface
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DebateContext:
    """Everything a provider needs to compose a single chef turn."""

    preferences: PreferenceInput
    user_block: str
    round_number: int
    agent: AgentName
    previous_argument: str | None


class ChefProvider:
    """Generate one chef argument and one final judge report."""

    def argument(
        self,
        ctx: DebateContext,
        *,
        session_id: UUID,
        request_id: str,
    ) -> AgentMessage:
        raise NotImplementedError

    def report(
        self,
        *,
        preferences: PreferenceInput,
        transcript: str,
        session_id: UUID,
        request_id: str,
    ) -> DebateReport:
        raise NotImplementedError


# --------------------------------------------------------------------------
# Real provider (SiliconFlow)
# --------------------------------------------------------------------------


class SiliconFlowChefProvider(ChefProvider):
    """Drive chefs and the judge through the SiliconFlow HTTP client.

    ``client`` owns bounded retries/backoff/timeout. ``call(prompt, system)``
    returns the raw assistant text; it is injectable so parsing and schema
    repair can be tested offline.
    """

    _SYSTEM = {
        AgentName.SICHUAN_SPICY: prompts.SICHUAN_SYSTEM_PROMPT,
        AgentName.CANTONESE_WELLNESS: prompts.CANTONESE_SYSTEM_PROMPT,
    }
    _LABEL = {
        AgentName.SICHUAN_SPICY: "川辣派",
        AgentName.CANTONESE_WELLNESS: "粤式养生派",
    }

    def __init__(
        self,
        client,
        *,
        call: Callable[[str, str | None], str],
    ) -> None:
        self._client = client
        self._call = call

    def _raw_output(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        session_id: UUID,
        request_id: str,
    ) -> str:
        started = utc_now()
        try:
            content = self._call(user_prompt, system_prompt)
        except Exception as exc:  # client raises typed errors; surface them
            raise DebateProviderError(f"model request failed: {exc}") from exc
        finally:
            latency_ms = round((utc_now() - started).total_seconds() * 1000, 1)
            LOGGER.info(
                "model request completed",
                extra={
                    "request_id": request_id,
                    "session_id": str(session_id),
                    "latency_ms": latency_ms,
                    "event": "model_reply",
                },
            )
        if not content or not content.strip():
            raise DebateProviderError("model returned an empty response")
        return content

    def argument(
        self,
        ctx: DebateContext,
        *,
        session_id: UUID,
        request_id: str,
    ) -> AgentMessage:
        user_prompt = prompts.debate_user_prompt(
            agent_side=self._LABEL[ctx.agent],
            round_number=ctx.round_number,
            taste=ctx.preferences.taste,
            budget_yuan=ctx.preferences.budget_yuan,
            weather=ctx.preferences.weather.value,
            companions=ctx.preferences.companions,
            user_block=ctx.user_block,
            previous_turn=ctx.previous_argument,
        )
        raw = self._raw_output(
            system_prompt=self._SYSTEM[ctx.agent],
            user_prompt=user_prompt,
            session_id=session_id,
            request_id=request_id,
        )
        obj = _require_object(raw, kind="chef")
        argument = str(obj.get("argument", "")).strip()
        evidence = str(obj.get("evidence", "")).strip()
        if not argument or not evidence:
            raise DebateProviderError("chef reply missing argument or evidence")
        return AgentMessage(
            round=ctx.round_number,
            agent=ctx.agent,
            argument=argument[:_MAX_TEXT_LEN],
            evidence=evidence[:_MAX_TEXT_LEN],
        )

    def report(
        self,
        *,
        preferences: PreferenceInput,
        transcript: str,
        session_id: UUID,
        request_id: str,
    ) -> DebateReport:
        user_prompt = prompts.judge_user_prompt(
            transcript=transcript,
            taste=preferences.taste,
            budget_yuan=preferences.budget_yuan,
            weather=preferences.weather.value,
            companions=preferences.companions,
            user_block=sanitise_user_text(preferences.taste),
        )
        raw = self._raw_output(
            system_prompt=prompts.JUDGE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            session_id=session_id,
            request_id=request_id,
        )
        obj = _require_object(raw, kind="judge")
        dish = str(obj.get("dish", "")).strip()
        cuisine = str(obj.get("cuisine", "")).strip()
        reason = str(obj.get("reason", "")).strip()
        if not dish or not reason:
            raise DebateProviderError("judge reply missing dish or reason")
        try:
            confidence = float(obj.get("confidence", 0.0))
        except (TypeError, ValueError):
            raise DebateProviderError("judge confidence is not numeric") from None
        breakdown = obj.get("score_breakdown", {}) or {}
        if not isinstance(breakdown, dict):
            raise DebateProviderError("judge score_breakdown must be an object")
        return DebateReport(
            dish=dish[:80],
            cuisine=cuisine if cuisine in ("sichuan", "cantonese") else "sichuan",
            reason=reason[: _MAX_TEXT_LEN * 2],
            confidence=max(0.0, min(confidence, 1.0)),
            score_breakdown=normalise_scores(breakdown),
        )


def _require_object(raw: str, *, kind: str) -> dict[str, Any]:
    """Parse one JSON object from model output with finite repair retries."""
    text = raw.strip()
    text = text.removeprefix("```json").removeprefix("```")
    text = text.removesuffix("```").strip()
    for _ in range(2):
        start, end = text.find("{"), text.rfind("}")
        candidate = text[start : end + 1] if start != -1 and end > start else text
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
        text = candidate
    raise SchemaRepairError(f"{kind} reply was not valid JSON")


def normalise_scores(breakdown: dict[str, Any]) -> dict[str, float]:
    """Coerce a 0..5 breakdown dict into clamped floats with known keys."""
    keys = ("taste", "budget", "weather", "debate")
    out: dict[str, float] = {}
    for key in keys:
        try:
            value = float(breakdown.get(key, 0.0))
        except (TypeError, ValueError):
            value = 0.0
        out[key] = max(0.0, min(value, 5.0))
    return out


# --------------------------------------------------------------------------
# Mock provider (deterministic, offline)
# --------------------------------------------------------------------------


class MockChefProvider(ChefProvider):
    """Deterministic chef + judge over the demo menu; no network required."""

    def argument(
        self,
        ctx: DebateContext,
        *,
        session_id: UUID,
        request_id: str,
    ) -> AgentMessage:
        del session_id, request_id
        side = _agent_side(ctx.agent)
        reasoner = MockReasoner(ctx.preferences)
        dish = reasoner.best_for_side(side, limit=1)[0]
        label = "川辣派" if side.value == "sichuan" else "粤式养生派"
        argument = (
            f"第 {ctx.round_number} 轮 · {label} 立场：推荐「{dish.item.name}」"
            f"（¥{dish.item.price_yuan}）。{_human_reasons(dish.reasons)}。"
        )
        evidence = (
            f"人均预算 {ctx.preferences.budget_yuan} 元 / "
            f"同行 {ctx.preferences.companions} 人"
        )
        if ctx.previous_argument:
            argument += " 针对对方观点，我补充自己的菜品依据。"
        return AgentMessage(
            round=ctx.round_number,
            agent=ctx.agent,
            argument=argument,
            evidence=evidence,
        )

    def report(
        self,
        *,
        preferences: PreferenceInput,
        transcript: str,
        session_id: UUID,
        request_id: str,
    ) -> DebateReport:
        del transcript, session_id, request_id
        reasoner = MockReasoner(preferences)
        best = reasoner.best_overall(limit=1)[0]
        runner_up = reasoner.best_overall(limit=2)
        fallback = runner_up[1] if len(runner_up) > 1 else None
        weather = preferences.weather
        breakdown = {
            "taste": round(5.0 * best.score, 2),
            "budget": 5.0 if best.item.price_yuan <= preferences.budget_yuan else 3.8,
            "weather": 4.5 if _weather_ok(weather, best.item) else 3.0,
            "debate": round(3.5 + 0.5 * best.score, 2),
        }
        reason = _human_reasons(best.reasons)
        if fallback is not None:
            reason += f"备选：{fallback.item.name}（¥{fallback.item.price_yuan}）。"
        return DebateReport(
            dish=best.item.name,
            cuisine=best.item.cuisine.value,
            reason=reason,
            confidence=round(max(0.0, min(best.score, 1.0)), 3),
            score_breakdown=breakdown,
        )


def _agent_side(agent: AgentName):
    from .domain import AgentSide

    return (
        AgentSide.SICHUAN if agent is AgentName.SICHUAN_SPICY else AgentSide.CANTONESE
    )


def _human_reasons(
    reasons: list[str], *, fallback: str = "风味、价格与天气综合最合适"
) -> str:
    return "；".join(reasons) if reasons else fallback


def _weather_ok(weather: Weather, item) -> bool:
    if weather in (Weather.COLD, Weather.RAINY):
        return item.heat_rating >= 3
    if weather is Weather.HOT:
        return item.heat_rating <= 2 and item.rich_level <= 2
    if weather is Weather.HUMID:
        return item.rich_level <= 2 and item.spice_level <= 1
    return True


# --------------------------------------------------------------------------
# SSE events
# --------------------------------------------------------------------------


@dataclass
class DebateEvent:
    """One immutable event streamed over SSE or replayed from storage."""

    event: str
    data: dict[str, Any]
    created_at: str = field(default_factory=lambda: utc_now().isoformat())

    def sse(self) -> str:
        payload = json.dumps(self.data, ensure_ascii=False, default=str)
        return f"event: {self.event}\ndata: {payload}\n\n"


def status_event(session_id: UUID, status: SessionStatus) -> DebateEvent:
    return DebateEvent(
        "status", {"session_id": str(session_id), "status": status.value}
    )


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------


class DebateService:
    """Create sessions, run debates, judge results and persist everything."""

    def __init__(
        self,
        database_url: str = "sqlite:///foodarena.db",
        *,
        in_memory: bool = False,
        default_provider: ProviderMode = ProviderMode.MOCK,
    ) -> None:
        self._engine = make_engine(database_url, in_memory=in_memory)
        create_all(self._engine)
        self._default_provider = default_provider

    # -- public API ---------------------------------------------------------
    def create_session(
        self,
        preferences: PreferenceInput,
        *,
        provider: ProviderMode | None = None,
    ) -> SessionView:
        session_id = uuid4()
        mode = (provider or self._default_provider).value
        with self._session() as db:
            row = SessionRow(
                session_id=str(session_id),
                status=SessionStatus.PENDING.value,
                provider=mode,
            )
            db.add(row)
            db.flush()
            db.add(
                PreferenceRow(
                    session_id=row.id,
                    taste=preferences.taste,
                    budget_yuan=preferences.budget_yuan,
                    weather=preferences.weather.value,
                    companions=preferences.companions,
                )
            )
            db.commit()
        return self.get_session(session_id)

    def run_debate(
        self,
        session_id: UUID,
        *,
        provider: ProviderMode | None = None,
    ) -> tuple[SessionView, list[DebateEvent]]:
        """Run the debate to a terminal state; return (final view, events)."""
        events: list[DebateEvent] = []
        views: list[SessionView] = []
        for view, event in self.stream_debate(session_id, provider=provider):
            views.append(view)
            events.append(event)
        if not views:  # pragma: no cover - stream_debate always yields a view
            raise AssertionError("stream_debate produced no view")
        return views[-1], events

    def stream_debate(
        self,
        session_id: UUID,
        *,
        provider: ProviderMode | None = None,
    ) -> Iterable[tuple[SessionView, DebateEvent]]:
        """Yield one (final-or-interim view, event) per debate step.

        The generator persists each chef message and reports the session view
        after every step so an SSE endpoint can forward events as they happen,
        instead of buffering the whole debate and flushing it at the end.
        """
        request_id = bind_request_id()
        mode = provider or self._default_provider

        # (1) claim the session as RUNNING
        with self._session() as db:
            row = self._fetch_row(db, session_id)
            if row is None:
                raise SessionNotFound(session_id)
            if row.status != SessionStatus.PENDING.value:
                # Re-entry / already finalised: return current stored state.
                view = row_to_domain(row)
                yield view, status_event(session_id, SessionStatus(row.status))
                return
            prefs = self._read_preferences(db, row)
            row.status = SessionStatus.RUNNING.value
            db.commit()

        yield (
            self.get_session(session_id),
            status_event(session_id, SessionStatus.RUNNING),
        )
        provider_obj = self._build_provider(mode)

        try:
            # (2) three rounds x two chefs, persisted one message at a time
            previous: str | None = None
            for round_number in range(1, ROUNDS + 1):
                for agent in (AgentName.SICHUAN_SPICY, AgentName.CANTONESE_WELLNESS):
                    yield (
                        self.get_session(session_id),
                        DebateEvent(
                            "round_started",
                            {"round": round_number, "agent": agent.value},
                        ),
                    )
                    ctx = DebateContext(
                        preferences=prefs,
                        user_block=sanitise_user_text(prefs.taste),
                        round_number=round_number,
                        agent=agent,
                        previous_argument=previous,
                    )
                    message = provider_obj.argument(
                        ctx, session_id=session_id, request_id=request_id
                    )
                    self._append_message(session_id, message)
                    view = self.get_session(session_id)
                    yield (
                        view,
                        DebateEvent(
                            "message",
                            {
                                "round": message.round,
                                "agent": message.agent.value,
                                "argument": message.argument,
                                "evidence": message.evidence,
                            },
                        ),
                    )
                    previous = f"{message.agent.value}: {message.argument}"

            # (3) validate (all six messages present) then judge
            self._set_status(session_id, SessionStatus.VALIDATING)
            yield (
                self.get_session(session_id),
                status_event(session_id, SessionStatus.VALIDATING),
            )

            transcript = self._build_transcript(session_id)
            report = provider_obj.report(
                preferences=prefs,
                transcript=transcript,
                session_id=session_id,
                request_id=request_id,
            )
            with self._session() as db:
                row = self._fetch_row(db, session_id)
                db.add(
                    RecommendationRow(
                        session_id=row.id,
                        dish=report.dish,
                        cuisine=report.cuisine,
                        reason=report.reason,
                        confidence=report.confidence,
                        score_breakdown_json=report.score_breakdown,
                    )
                )
                row.status = SessionStatus.SUCCESS.value
                row.failure_reason = None
                db.commit()

            view = self.get_session(session_id)
            yield (
                view,
                DebateEvent(
                    "report",
                    {"session_id": str(session_id), "report": report.model_dump()},
                ),
            )
            yield view, status_event(session_id, SessionStatus.SUCCESS)

        except SessionNotFound:
            raise
        except Exception as exc:  # noqa: BLE001 - any provider/schema/db fault
            reason = redact_secrets(str(exc))[:200]
            LOGGER.error(
                "debate failed: %s",
                reason,
                extra={
                    "request_id": request_id,
                    "session_id": str(session_id),
                    "event": "debate_failed",
                },
            )
            with self._session() as db:
                row = self._fetch_row(db, session_id)
                if row is not None and row.status not in (
                    SessionStatus.SUCCESS.value,
                    SessionStatus.FAILED.value,
                ):
                    row.status = SessionStatus.FAILED.value
                    row.failure_reason = reason
                    db.commit()
            view = self.get_session(session_id)
            yield view, status_event(session_id, SessionStatus.FAILED)

    def get_session(self, session_id: UUID) -> SessionView:
        with self._session() as db:
            row = self._fetch_row(db, session_id)
            if row is None:
                raise SessionNotFound(session_id)
            return row_to_domain(row)

    def replay_events(self, session_id: UUID) -> list[DebateEvent]:
        """Rebuild an SSE-style event list from a stored session."""
        with self._session() as db:
            row = self._fetch_row(db, session_id)
            if row is None:
                raise SessionNotFound(session_id)
            messages = list(row.messages)
            status = SessionStatus(row.status)
            recommendation = row.recommendation

        events = [status_event(session_id, status)]
        for message in messages:
            events.append(
                DebateEvent(
                    "message",
                    {
                        "round": message.round,
                        "agent": message.agent,
                        "argument": message.argument,
                        "evidence": message.evidence,
                    },
                )
            )
        if status is SessionStatus.SUCCESS and recommendation is not None:
            report = DebateReport(
                dish=recommendation.dish,
                cuisine=recommendation.cuisine,
                reason=recommendation.reason,
                confidence=recommendation.confidence,
                score_breakdown=dict(recommendation.score_breakdown_json),
            )
            events.append(
                DebateEvent(
                    "report",
                    {"session_id": str(session_id), "report": report.model_dump()},
                )
            )
        return events

    # -- persistence helpers -------------------------------------------------
    def _session(self) -> OrmSession:
        return OrmSession(self._engine)

    def _fetch_row(self, db: OrmSession, session_id: UUID) -> SessionRow | None:
        return db.scalar(
            select(SessionRow).where(SessionRow.session_id == str(session_id))
        )

    def _read_preferences(self, db: OrmSession, row: SessionRow) -> PreferenceInput:
        pref = row.preference
        return PreferenceInput(
            taste=pref.taste,
            budget_yuan=pref.budget_yuan,
            weather=Weather(pref.weather),
            companions=pref.companions,
        )

    def _set_status(self, session_id: UUID, status: SessionStatus) -> None:
        with self._session() as db:
            row = self._fetch_row(db, session_id)
            row.status = status.value
            db.commit()

    def _append_message(self, session_id: UUID, message: AgentMessage) -> None:
        with self._session() as db:
            row = self._fetch_row(db, session_id)
            db.add(
                MessageRow(
                    session_id=row.id,
                    round=message.round,
                    agent=message.agent.value,
                    argument=message.argument,
                    evidence=message.evidence,
                )
            )
            db.commit()

    def _build_transcript(self, session_id: UUID) -> str:
        """Return a readable six-line transcript for the judge prompt."""
        with self._session() as db:
            row = self._fetch_row(db, session_id)
            messages = list(row.messages)
        labels = {
            AgentName.SICHUAN_SPICY.value: "川辣派",
            AgentName.CANTONESE_WELLNESS.value: "粤式养生派",
        }
        lines = [
            (
                f"第{m.round}轮 {labels.get(m.agent, m.agent)}：{m.argument}"
                f"（佐证：{m.evidence}）"
            )
            for m in messages
        ]
        return "\n".join(lines)

    def _build_provider(self, provider: ProviderMode) -> ChefProvider:
        if provider is ProviderMode.REAL:
            from .providers import build_real_provider

            return build_real_provider()
        return MockChefProvider()
