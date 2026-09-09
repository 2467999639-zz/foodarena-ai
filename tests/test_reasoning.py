"""Tests for the deterministic mock reasoner (menu scoring)."""

from __future__ import annotations

from foodarena_ai.domain import AgentSide, PreferenceInput, Weather
from foodarena_ai.reasoning import MockReasoner


def _reasoner(
    taste: str, budget: int = 15, weather: Weather = Weather.SUNNY, n: int = 2
):
    return MockReasoner(
        PreferenceInput(taste=taste, budget_yuan=budget, weather=weather, companions=n)
    )


def test_spicy_user_prefers_sichuan_side() -> None:
    sides = _reasoner("麻辣").top_cuisines()
    assert sides[0] is AgentSide.SICHUAN


def test_light_user_prefers_cantonese_side() -> None:
    sides = _reasoner("清淡").top_cuisines()
    assert sides[0] is AgentSide.CANTONESE


def test_unknown_taste_keeps_both_sides_competitive() -> None:
    sides = _reasoner("随便吃").top_cuisines()
    assert set(sides) == {AgentSide.SICHUAN, AgentSide.CANTONESE}


def test_best_for_side_respects_budget() -> None:
    reasoner = _reasoner("清淡", budget=10)
    dishes = reasoner.best_for_side(AgentSide.SICHUAN, limit=3)
    assert dishes
    for scored in dishes:
        assert scored.item.price_yuan <= 10 or scored.item.price_yuan <= 10 * 1.2


def test_cold_weather_biases_toward_hot_dishes() -> None:
    reasoner = _reasoner("随便", budget=25, weather=Weather.COLD)
    best = reasoner.best_overall(limit=1)[0]
    assert best.item.heat_rating >= 2


def test_hot_weather_avoids_oily_dishes() -> None:
    reasoner = _reasoner("随便", budget=25, weather=Weather.HOT)
    best = reasoner.best_overall(limit=1)[0]
    assert best.item.rich_level <= 2


def test_best_overall_returns_scored_dish_with_reasons() -> None:
    scored = _reasoner("麻辣").best_overall(limit=1)[0]
    assert scored.item.name
    assert 0 <= scored.score <= 1
    assert isinstance(scored.reasons, list)
