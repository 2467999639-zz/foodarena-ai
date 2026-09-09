"""Domain contracts for the FoodArena debate application.

These Pydantic models are the single source of truth shared by the API layer,
the persistence layer, the debate/judge services and the automated tests. Any
external model output crosses a Pydantic boundary before it is trusted.
"""

from __future__ import annotations

import enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SessionStatus(enum.StrEnum):
    """Lifecycle states of a debate session."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    VALIDATING = "VALIDATING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class AgentName(enum.StrEnum):
    """Stable identifiers for the two debating chefs and the judge."""

    SICHUAN_SPICY = "sichuan_spicy"
    CANTONESE_WELLNESS = "cantonese_wellness"
    JUDGE = "judge"


class AgentSide(enum.StrEnum):
    """Presentational label for the two persona camps."""

    SICHUAN = "sichuan"
    CANTONESE = "cantonese"


class Weather(enum.StrEnum):
    """Supported weather conditions for menu reasoning."""

    SUNNY = "sunny"
    RAINY = "rainy"
    COLD = "cold"
    HOT = "hot"
    HUMID = "humid"


class ProviderMode(enum.StrEnum):
    """How a debate obtains model output."""

    REAL = "real"  # SiliconFlow via the LLM adapter
    MOCK = "mock"  # deterministic local reasoning, no network access


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


class PreferenceInput(BaseModel):
    """User-provided constraints that seed a debate."""

    model_config = ConfigDict(str_strip_whitespace=True)

    taste: str = Field(min_length=1, max_length=60)
    budget_yuan: int = Field(ge=1, le=200)
    weather: Weather
    companions: int = Field(ge=1, le=20)


class DebateStartRequest(BaseModel):
    """Optional body accepted by the debate endpoint."""

    provider: ProviderMode | None = None


# --------------------------------------------------------------------------
# Debate output
# --------------------------------------------------------------------------


class AgentArgument(BaseModel):
    """Structured content produced by one chef for one turn."""

    model_config = ConfigDict(frozen=True)

    argument: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class AgentMessage(AgentArgument):
    """A recorded message inside a debate session."""

    model_config = ConfigDict(frozen=True)

    round: int = Field(ge=1, le=3)
    agent: AgentName


class DebateReport(BaseModel):
    """Final judgement produced after the three rounds complete."""

    dish: str = Field(min_length=1)
    cuisine: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    score_breakdown: dict[str, float]


class SessionView(BaseModel):
    """Public snapshot of a debate session returned to clients."""

    session_id: UUID
    status: SessionStatus
    messages: list[AgentMessage] = Field(default_factory=list)
    report: DebateReport | None = None
    failure_reason: str | None = None


class SessionSummary(BaseModel):
    """Body returned when a session is created."""

    session_id: UUID
    status: SessionStatus


class ErrorResponse(BaseModel):
    """Structured error body used across the API."""

    error: str = Field(min_length=1)


# --------------------------------------------------------------------------
# Demo menu (synthetic data, no real student information)
# --------------------------------------------------------------------------


class MenuItem(BaseModel):
    """One synthetic canteen dish used to ground arguments and scoring."""

    model_config = ConfigDict(frozen=True)

    name: str
    cuisine: AgentSide
    price_yuan: int = Field(ge=1)
    spice_level: int = Field(ge=0, le=3)  # 0 = none .. 3 = very hot
    rich_level: int = Field(ge=1, le=3)  # how heavy / oily the dish is
    heat_rating: int = Field(ge=1, le=3)  # warmth generated, 3 = hottest
    prep_minutes: int = Field(ge=1)
    vegetarian: bool = False
    tags: list[str] = Field(default_factory=list)


MENU: list[MenuItem] = [
    MenuItem(
        name="川味小面",
        cuisine=AgentSide.SICHUAN,
        price_yuan=10,
        spice_level=3,
        rich_level=2,
        heat_rating=3,
        prep_minutes=8,
        tags=["辣", "红油", "暖胃"],
    ),
    MenuItem(
        name="口水鸡套饭",
        cuisine=AgentSide.SICHUAN,
        price_yuan=18,
        spice_level=3,
        rich_level=2,
        heat_rating=2,
        prep_minutes=12,
        tags=["辣", "凉菜", "下饭"],
    ),
    MenuItem(
        name="麻辣香锅",
        cuisine=AgentSide.SICHUAN,
        price_yuan=22,
        spice_level=3,
        rich_level=3,
        heat_rating=3,
        prep_minutes=15,
        tags=["辣", "重油", "多人"],
    ),
    MenuItem(
        name="宫保鸡丁饭",
        cuisine=AgentSide.SICHUAN,
        price_yuan=15,
        spice_level=2,
        rich_level=2,
        heat_rating=2,
        prep_minutes=10,
        tags=["微辣", "酸甜", "均衡"],
    ),
    MenuItem(
        name="凉拌鸡丝面",
        cuisine=AgentSide.SICHUAN,
        price_yuan=12,
        spice_level=2,
        rich_level=1,
        heat_rating=1,
        prep_minutes=6,
        tags=["凉面", "清爽", "开胃"],
    ),
    MenuItem(
        name="粤式烧腊饭",
        cuisine=AgentSide.CANTONESE,
        price_yuan=20,
        spice_level=0,
        rich_level=2,
        heat_rating=2,
        prep_minutes=10,
        tags=["烧腊", "咸甜", "温补"],
    ),
    MenuItem(
        name="皮蛋瘦肉粥",
        cuisine=AgentSide.CANTONESE,
        price_yuan=9,
        spice_level=0,
        rich_level=1,
        heat_rating=3,
        prep_minutes=9,
        tags=["粥", "养胃", "清淡"],
    ),
    MenuItem(
        name="豉汁蒸鸡饭",
        cuisine=AgentSide.CANTONESE,
        price_yuan=19,
        spice_level=0,
        rich_level=2,
        heat_rating=2,
        prep_minutes=13,
        tags=["蒸", "少油", "温补"],
    ),
    MenuItem(
        name="香菇滑鸡煲仔饭",
        cuisine=AgentSide.CANTONESE,
        price_yuan=21,
        spice_level=0,
        rich_level=2,
        heat_rating=3,
        prep_minutes=16,
        tags=["煲仔", "香", "暖胃"],
    ),
    MenuItem(
        name="老火例汤套餐",
        cuisine=AgentSide.CANTONESE,
        price_yuan=16,
        spice_level=0,
        rich_level=1,
        heat_rating=2,
        prep_minutes=8,
        tags=["汤", "养生", "清淡"],
    ),
    MenuItem(
        name="玉米排骨汤面",
        cuisine=AgentSide.CANTONESE,
        price_yuan=14,
        spice_level=0,
        rich_level=1,
        heat_rating=3,
        prep_minutes=10,
        tags=["汤面", "清甜", "暖胃"],
    ),
    MenuItem(
        name="清炒时蔬配饭",
        cuisine=AgentSide.CANTONESE,
        price_yuan=8,
        spice_level=0,
        rich_level=1,
        heat_rating=1,
        prep_minutes=7,
        vegetarian=True,
        tags=["素", "清淡", "低脂"],
    ),
]
