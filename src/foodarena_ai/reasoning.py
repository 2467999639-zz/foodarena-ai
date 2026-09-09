"""Deterministic mock reasoning over a menu catalog.

``MockReasoner`` scores every dish in the supplied catalog (built-in synthetic
menu or a loaded real-menu file) against the user preferences with explainable
rules and returns grounded picks without any model call. This powers the
``mock`` provider path (deterministic, offline, CI-safe).
"""

from __future__ import annotations

from dataclasses import dataclass

from .domain import (
    BUILTIN_MENU,
    AgentSide,
    MenuCatalog,
    MenuItem,
    PreferenceInput,
    Weather,
)

# --------------------------------------------------------------------------
# Menu scoring
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoredDish:
    item: MenuItem
    score: float
    reasons: list[str]


class MockReasoner:
    """Score a menu against preferences with explainable rules."""

    # How closely each menu cuisine matches a declared taste. Unknown tastes
    # default to a neutral mapping so both sides stay competitive.
    _TASTE_MATCH: dict[str, dict[AgentSide, float]] = {
        "麻辣": {AgentSide.SICHUAN: 1.0, AgentSide.CANTONESE: 0.0},
        "特辣": {AgentSide.SICHUAN: 1.0, AgentSide.CANTONESE: 0.0},
        "酸辣": {AgentSide.SICHUAN: 0.9, AgentSide.CANTONESE: 0.2},
        "微辣": {AgentSide.SICHUAN: 0.8, AgentSide.CANTONESE: 0.4},
        "清淡": {AgentSide.SICHUAN: 0.1, AgentSide.CANTONESE: 0.95},
        "酸甜": {AgentSide.SICHUAN: 0.6, AgentSide.CANTONESE: 0.7},
        "重口": {AgentSide.SICHUAN: 0.9, AgentSide.CANTONESE: 0.3},
    }
    _NEUTRAL = {AgentSide.SICHUAN: 0.55, AgentSide.CANTONESE: 0.6}
    _PRICE_TOLERANCE = 0.2  # generous-ish: up to +20% over budget still scored

    def __init__(
        self,
        preferences: PreferenceInput,
        *,
        menu: MenuCatalog = BUILTIN_MENU,
    ) -> None:
        self._prefs = preferences
        self._menu = menu

    @property
    def items(self) -> list[MenuItem]:
        return [item for item in self._menu.items if item.available]

    def top_cuisines(self) -> list[AgentSide]:
        """Return the two sides ordered by taste fit for this user."""
        return sorted(
            [AgentSide.SICHUAN, AgentSide.CANTONESE],
            key=lambda s: self._cuisine_match(s),
            reverse=True,
        )

    def _cuisine_match(self, side: AgentSide) -> float:
        taste = self._prefs.taste.lower()
        for keyword, mapping in self._TASTE_MATCH.items():
            if keyword in taste:
                return mapping[side]
        return self._NEUTRAL[side]

    def best_for_side(self, side: AgentSide, limit: int = 1) -> list[ScoredDish]:
        """Highest-scoring affordable-ish dishes for one side."""
        scored = [self._score(item) for item in self.items if item.cuisine is side]
        affordable = [s for s in scored if s.item.price_yuan <= self._prefs.budget_yuan]
        candidates = affordable or scored  # soft cap: allow slight overruns
        ranked = sorted(candidates, key=lambda s: s.score, reverse=True)
        return ranked[:limit]

    def best_overall(self, limit: int = 1) -> list[ScoredDish]:
        """Highest-scoring dishes across the whole menu."""
        candidates = [
            s
            for s in (self._score(item) for item in self.items)
            if s.item.price_yuan <= self._prefs.budget_yuan
        ]
        ranked = sorted(candidates, key=lambda s: s.score, reverse=True)
        return ranked[:limit]

    def _score(self, item: MenuItem) -> ScoredDish:
        prefs = self._prefs
        reasons: list[str] = []

        taste_score = 0.0
        match = self._cuisine_match(item.cuisine)
        # "麻辣" means genuinely hot dishes; "清淡" means mild ones.
        if "辣" in prefs.taste.lower() or "麻辣" in prefs.taste.lower():
            if item.spice_level >= 2:
                taste_score = 1.0
                reasons.append(f"{item.name} 辣度对味")
            else:
                taste_score = 0.2 * match
        elif "清淡" in prefs.taste.lower() or "养生" in prefs.taste.lower():
            if item.spice_level <= 1 and item.rich_level <= 2:
                taste_score = 1.0
                reasons.append(f"{item.name} 清淡少油")
            else:
                taste_score = 0.2
        else:
            taste_score = match
            if item.tags and _looks_like_flavour(prefs.taste):
                reasons.append(f"{item.name} 风味契合「{prefs.taste}」")

        budget = min(
            1.0,
            max(
                0.0, 1.0 - abs(item.price_yuan - prefs.budget_yuan) / prefs.budget_yuan
            ),
        )
        if item.price_yuan <= prefs.budget_yuan:
            budget = 1.0
            reasons.append("价格在预算内")
        elif item.price_yuan <= prefs.budget_yuan * (1 + self._PRICE_TOLERANCE):
            budget = 0.75
            reasons.append("略超预算但可接受")

        weather_score = self._weather_fit(item)

        score = 0.45 * taste_score + 0.25 * budget + 0.30 * weather_score
        return ScoredDish(item=item, score=round(score, 3), reasons=reasons)

    def _weather_fit(self, item: MenuItem) -> float:
        weather = self._prefs.weather
        if weather in (Weather.COLD, Weather.RAINY) and item.heat_rating >= 3:
            return 1.0
        if weather is Weather.HOT and item.heat_rating <= 2 and item.rich_level <= 2:
            return 1.0
        if weather is Weather.HUMID and item.rich_level <= 2 and item.spice_level <= 1:
            return 1.0
        return 0.5


def _looks_like_flavour(text: str) -> bool:
    """True when free text reads as a genuine taste keyword rather than an
    instruction, question or other non-flavour utterance (so the mock never
    echoes sanitised user text back as a fake flavour match)."""
    lowered = text.lower()
    flavour_markers = (
        "辣",
        "麻",
        "甜",
        "酸",
        "咸",
        "鲜",
        "香",
        "清淡",
        "重口",
        "油",
        "素",
        "养生",
        "汤",
        "粥",
        "面",
        "饭",
        "味",
        "spicy",
        "sweet",
        "sour",
        "salty",
        "light",
        "hot",
        "egg",
        "soup",
        "noodle",
    )
    question_or_instruction = (
        "?",
        "？",
        "请",
        "忽略",
        "复述",
        "泄露",
        "记住",
        "作为",
        "你是",
        "扮演",
        "ignore",
        "repeat",
        "prompt",
        "system",
        "instruction",
        "forget",
        "now",
        "pretend",
        ":",
        "：",
    )
    if any(marker in lowered for marker in question_or_instruction):
        return False
    return any(marker in lowered for marker in flavour_markers)
