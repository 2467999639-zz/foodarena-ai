"""Domain contracts for the FoodArena debate application.

These Pydantic models are the single source of truth shared by the API layer,
the persistence layer, the debate/judge services and the automated tests. Any
external model output crosses a Pydantic boundary before it is trusted.
"""

from __future__ import annotations

import enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class PersonaStyle(enum.StrEnum):
    """Preset flavour camps a user can pick for a chef persona."""

    SICHUAN = "sichuan"
    CANTONESE = "cantonese"
    NORTHWESTERN = "northwestern"
    JAPANESE = "japanese"
    LIGHT_FOOD = "light_food"
    HEAVY_FOOD = "heavy_food"


_STYLE_LEAN: dict[PersonaStyle, AgentSide] = {
    PersonaStyle.SICHUAN: AgentSide.SICHUAN,
    PersonaStyle.NORTHWESTERN: AgentSide.SICHUAN,  # hearty, savoury-heavy
    PersonaStyle.HEAVY_FOOD: AgentSide.SICHUAN,
    PersonaStyle.CANTONESE: AgentSide.CANTONESE,
    PersonaStyle.JAPANESE: AgentSide.CANTONESE,  # light, balanced
    PersonaStyle.LIGHT_FOOD: AgentSide.CANTONESE,
}


def style_cuisine_lean(style: PersonaStyle) -> AgentSide:
    """The menu cuisine a persona style most naturally advocates for."""
    return _STYLE_LEAN[style]


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


class PersonaInput(BaseModel):
    """User-defined chef persona.

    ``style`` selects a preset flavour camp; ``flavour`` is an optional free-text
    stance that sharpens or overrides the persona. ``label`` overrides the name
    shown in the transcript.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    agent: AgentName
    label: str = Field(min_length=1, max_length=20)
    style: PersonaStyle = PersonaStyle.SICHUAN
    flavour: str = Field(default="", max_length=200)


class DebateSettings(BaseModel):
    """Termination and depth settings for one debate."""

    min_rounds: int = Field(default=2, ge=1, le=3)
    max_rounds: int = Field(default=3, ge=1, le=3)
    early_stop: bool = True

    def model_post_init(self, __context: object) -> None:
        if self.min_rounds > self.max_rounds:
            raise ValueError("min_rounds must not exceed max_rounds")


class DebateStartRequest(BaseModel):
    """Optional body accepted by the debate endpoint."""

    provider: ProviderMode | None = None
    personas: list[PersonaInput] = Field(default_factory=list)
    settings: DebateSettings | None = None


class SessionCreateRequest(BaseModel):
    """Body accepted by POST /sessions.

    Accepts either the extended shape ``{preferences: {...}, personas: [...],
    settings: {...}}`` used by the custom-persona UI, or a flat preference body
    (``{taste, budget_yuan, weather, companions}``) for backward compatibility.
    ``personas``/``settings`` are persisted on the session at creation so the
    debate (run via SSE or the debate endpoint) picks them up automatically.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    preferences: PreferenceInput | None = None
    personas: list[PersonaInput] = Field(default_factory=list)
    settings: DebateSettings | None = None

    @model_validator(mode="before")
    @classmethod
    def lift_flat_preferences(cls, data: Any) -> Any:
        if isinstance(data, dict) and "preferences" not in data:
            # Flat preference body: lift its keys into the nested shape.
            flat_keys = {
                "taste",
                "budget_yuan",
                "weather",
                "companions",
            }
            if flat_keys.intersection(data):
                data = {"preferences": data}
        return data

    def resolved(
        self,
    ) -> tuple[PreferenceInput, list[PersonaInput], DebateSettings | None]:
        if self.preferences is None:
            raise ValueError("preferences are required")
        return self.preferences, self.personas, self.settings


# --------------------------------------------------------------------------
# Persona defaults
# --------------------------------------------------------------------------

#: The persona the SICHUAN chef falls back to when the caller supplies none.
SICHUAN_DEFAULT_PERSONA = PersonaInput(
    agent=AgentName.SICHUAN_SPICY,
    label="川辣派",
    style=PersonaStyle.SICHUAN,
)

#: The persona the CANTONESE chef falls back to when the caller supplies none.
CANTONESE_DEFAULT_PERSONA = PersonaInput(
    agent=AgentName.CANTONESE_WELLNESS,
    label="粤式养生派",
    style=PersonaStyle.CANTONESE,
)

#: agent.value -> display label for the two debating chefs.
DEFAULT_PERSONA_LABELS: dict[str, str] = {
    AgentName.SICHUAN_SPICY.value: SICHUAN_DEFAULT_PERSONA.label,
    AgentName.CANTONESE_WELLNESS.value: CANTONESE_DEFAULT_PERSONA.label,
}


def default_personas() -> dict[AgentName, PersonaInput]:
    """Return the built-in personas keyed by chef agent."""
    return {
        AgentName.SICHUAN_SPICY: SICHUAN_DEFAULT_PERSONA,
        AgentName.CANTONESE_WELLNESS: CANTONESE_DEFAULT_PERSONA,
    }


def persona_label_map(personas: dict[AgentName, PersonaInput]) -> dict[str, str]:
    """Map ``agent.value`` -> display ``label`` for a resolved persona set.

    Unknown agents are skipped; a default label is used when a persona has no
    readable label of its own.
    """
    labels = dict(DEFAULT_PERSONA_LABELS)
    for agent, persona in personas.items():
        label = (persona.label or "").strip()
        if label:
            labels[agent.value] = label
    return labels


def persona_input_from_dict(raw: dict[str, Any]) -> PersonaInput | None:
    """Rehydrate one :class:`PersonaInput` from a stored JSON dict.

    Returns ``None`` for malformed rows so old/corrupt stored data degrades to
    the built-in default instead of breaking the read path.
    """
    try:
        return PersonaInput.model_validate(raw)
    except (TypeError, ValueError):
        return None


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
    # agent.value -> display label, resolved from the stored personas (or the
    # built-in defaults when none were configured).
    personas: dict[str, str] = Field(default_factory=dict)


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
    # Real-menu fields (optional): keep the built-in sample simple while a
    # loaded menu file can mark delivery, service window and source.
    available: bool = True
    delivery_only: bool = False
    source: Literal["canteen", "takeaway", "sample"] = "sample"


class MenuCatalog(BaseModel):
    """A validated, loadable menu with metadata about its origin."""

    source_label: str = Field(min_length=1)
    items: list[MenuItem] = Field(min_length=1)


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

BUILTIN_MENU = MenuCatalog(
    source_label="内置合成样例菜单",
    items=[item for item in MENU],
)


def menu_from_items(
    items: list[MenuItem], *, source_label: str = "自定义菜单"
) -> MenuCatalog:
    return MenuCatalog(source_label=source_label, items=list(items))
