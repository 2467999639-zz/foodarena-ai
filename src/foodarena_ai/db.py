"""SQLite persistence for FoodArena debate sessions.

Schema tables (normalised from the ER design in docs/system_design.md):

    sessions(id PK, session_id UUID UNIQUE, status TEXT, provider TEXT,
             created_at, updated_at, failure_reason)
    preferences(id PK, session_id FK->sessions, taste, budget_yuan, weather,
                companions, created_at)  -- UNIQUE(session_id): one per session
    messages(id PK, session_id FK->sessions, round, agent, argument, evidence,
             created_at)                -- ordered by id
    recommendations(id PK, session_id FK->sessions, dish, cuisine, reason,
                    confidence, score_breakdown_json, created_at)
                                        -- UNIQUE(session_id): one final report
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.pool import StaticPool

from .domain import AgentName, ProviderMode, SessionStatus, Weather


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    provider: Mapped[str] = mapped_column(String(8), default=ProviderMode.MOCK.value)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON-encoded personas (agent -> PersonaInput) and DebateSettings chosen at
    # debate start. Nullable so pre-existing databases (rows without these
    # columns) survive: NULL is treated as "use built-in defaults".
    personas_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    settings_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    preference: Mapped[PreferenceRow | None] = relationship(
        back_populates="session", uselist=False, cascade="all, delete-orphan"
    )
    messages: Mapped[list[MessageRow]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="MessageRow.id",
    )
    recommendation: Mapped[RecommendationRow | None] = relationship(
        back_populates="session", uselist=False, cascade="all, delete-orphan"
    )


class PreferenceRow(Base):
    __tablename__ = "preferences"
    __table_args__ = (UniqueConstraint("session_id", name="uq_pref_session"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    taste: Mapped[str] = mapped_column(String(60))
    budget_yuan: Mapped[int] = mapped_column(Integer)
    weather: Mapped[str] = mapped_column(String(10))
    companions: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    session: Mapped[SessionRow] = relationship(back_populates="preference")


class MessageRow(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    round: Mapped[int] = mapped_column(Integer)
    agent: Mapped[str] = mapped_column(String(24))
    argument: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    session: Mapped[SessionRow] = relationship(back_populates="messages")


class RecommendationRow(Base):
    __tablename__ = "recommendations"
    __table_args__ = (UniqueConstraint("session_id", name="uq_rec_session"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    dish: Mapped[str] = mapped_column(String(80))
    cuisine: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    score_breakdown_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    session: Mapped[SessionRow] = relationship(back_populates="recommendation")


def make_engine(database_url: str, *, in_memory: bool = False):
    """Create an engine; in-memory mode uses a shared StaticPool for tests."""
    if in_memory:
        return create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
    return create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        future=True,
    )


def create_all(engine) -> None:
    Base.metadata.create_all(engine)


#: (table, column, DDL) additive columns backfilled for pre-existing databases.
_ADDITIVE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("sessions", "personas_json", "TEXT"),
    ("sessions", "settings_json", "TEXT"),
)


def ensure_session_schema(engine) -> None:
    """Best-effort additive migration for an existing ``sessions`` table.

    ``create_all`` already adds the new columns for fresh databases; this only
    covers a pre-existing ``foodarena.db`` file that predates the persona /
    settings columns. Each ``ALTER TABLE`` is guarded so a failure (e.g. an
    unsupported engine or a racing writer) never breaks service startup.
    """
    try:
        existing = {
            column["name"] for column in inspect(engine).get_columns("sessions")
        }
    except Exception:  # noqa: BLE001 - table may not exist yet; nothing to migrate
        return
    with engine.begin() as connection:
        for _table, column, ddl_type in _ADDITIVE_COLUMNS:
            if column in existing:
                continue
            try:
                connection.execute(
                    text(f"ALTER TABLE sessions ADD COLUMN {column} {ddl_type}")
                )
            except Exception:  # noqa: BLE001 - column added by a concurrent writer
                continue


# --------------------------------------------------------------------------
# Repository helpers (row <-> domain mapping)
# --------------------------------------------------------------------------


def row_to_domain(session: SessionRow):
    """Map an ORM session row plus its relations to a domain SessionView."""
    from .domain import (
        AgentMessage,
        DebateReport,
        SessionStatus,
        SessionView,
        persona_label_map,
    )

    messages = [
        AgentMessage(
            round=row.round,
            agent=AgentName(row.agent),
            argument=row.argument,
            evidence=row.evidence,
        )
        for row in session.messages
    ]
    report = None
    if session.recommendation is not None:
        report = DebateReport(
            dish=session.recommendation.dish,
            cuisine=session.recommendation.cuisine,
            reason=session.recommendation.reason,
            confidence=session.recommendation.confidence,
            score_breakdown=dict(session.recommendation.score_breakdown_json),
        )
    personas = decode_personas(session.personas_json)
    return SessionView(
        session_id=session.session_id,
        status=SessionStatus(session.status),
        messages=messages,
        report=report,
        failure_reason=session.failure_reason,
        personas=persona_label_map(personas),
    )


def encode_personas(personas: dict) -> str | None:
    """Encode a resolved persona map to a stable JSON string for storage."""
    if not personas:
        return None
    return json.dumps(
        {agent.value: persona.model_dump() for agent, persona in personas.items()},
        ensure_ascii=False,
    )


def decode_personas(raw: str | None) -> dict:
    """Decode stored personas JSON back into a persona map (defaults on bad data)."""
    from .domain import AgentName, default_personas, persona_input_from_dict

    defaults = default_personas()
    if not raw:
        return defaults
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return defaults
    if not isinstance(data, dict):
        return defaults
    resolved: dict = {}
    for key, value in data.items():
        try:
            agent = AgentName(key)
        except ValueError:
            continue
        if agent not in defaults:
            continue  # JUDGE / unknown agents are never debated
        if not isinstance(value, dict):
            continue
        persona = persona_input_from_dict(value)
        if persona is None or persona.agent is not agent:
            continue
        resolved[agent] = persona
    for agent, persona in defaults.items():
        resolved.setdefault(agent, persona)
    return resolved


def encode_settings(settings) -> str | None:
    """Encode a DebateSettings instance to JSON (``None`` -> ``None``)."""
    if settings is None:
        return None
    return json.dumps(settings.model_dump(), ensure_ascii=False)


def decode_settings(raw: str | None):
    """Decode stored settings JSON back into a DebateSettings (default on bad)."""
    from .domain import DebateSettings

    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return DebateSettings.model_validate(data)
    except (TypeError, ValueError):
        return None


# Re-export for convenience
__all__ = [
    "AgentName",
    "Base",
    "MessageRow",
    "PreferenceRow",
    "ProviderMode",
    "RecommendationRow",
    "SessionRow",
    "SessionStatus",
    "Weather",
    "create_all",
    "decode_personas",
    "decode_settings",
    "encode_personas",
    "encode_settings",
    "ensure_session_schema",
    "make_engine",
    "row_to_domain",
    "utc_now",
]
