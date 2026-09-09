"""Tests for the Sprint 3-4 extension goals.

Covers custom Agent personas (label/style/flavour), the early-termination
"convergence" rule, loadable real-menu catalogs, and the menu endpoint.
Everything runs offline with the deterministic mock provider.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from foodarena_ai.domain import (
    AgentName,
    DebateSettings,
    PersonaInput,
    PersonaStyle,
    PreferenceInput,
    Weather,
)
from foodarena_ai.menu_store import load_menu
from foodarena_ai.service import DebateService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prefs(**overrides) -> PreferenceInput:
    values = dict(taste="麻辣", budget_yuan=15, weather=Weather.RAINY, companions=2)
    values.update(overrides)
    return PreferenceInput.model_validate(values)


def _persona(agent: AgentName, label: str, style: str, flavour: str = "") -> dict:
    return {
        "agent": agent.value,
        "label": label,
        "style": style,
        "flavour": flavour,
    }


def _api(service: DebateService) -> TestClient:
    import foodarena_ai.main as main

    def override():
        return service

    main.app.dependency_overrides[main.get_service] = override
    return TestClient(main.app)


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------


def test_personas_accepted_at_creation_and_surface_labels() -> None:
    service = DebateService(in_memory=True)
    client = _api(service)
    payload = {
        "preferences": _prefs(taste="清淡").model_dump(),
        "personas": [
            _persona(AgentName.SICHUAN_SPICY, "西北老铁", "northwestern"),
            _persona(AgentName.CANTONESE_WELLNESS, "汤奶奶", "cantonese"),
        ],
    }
    sid = client.post("/api/v1/sessions", json=payload).json()["session_id"]
    body = client.post(f"/api/v1/sessions/{sid}/debate").json()
    assert body["status"] == "SUCCESS"
    assert body["personas"] == {
        "sichuan_spicy": "西北老铁",
        "cantonese_wellness": "汤奶奶",
    }
    # The mock echoes the persona label into each argument.
    assert any("西北老铁" in m["argument"] for m in body["messages"])
    assert any("汤奶奶" in m["argument"] for m in body["messages"])


def test_personas_default_when_omitted() -> None:
    service = DebateService(in_memory=True)
    client = _api(service)
    sid = client.post("/api/v1/sessions", json=_prefs().model_dump()).json()[
        "session_id"
    ]
    body = client.post(f"/api/v1/sessions/{sid}/debate").json()
    assert body["personas"] == {
        "sichuan_spicy": "川辣派",
        "cantonese_wellness": "粤式养生派",
    }


def test_settings_persist_and_reentry_uses_them() -> None:
    """Settings supplied at create are used even when debate is run bare."""
    service = DebateService(in_memory=True)
    client = _api(service)
    payload = {
        "preferences": _prefs().model_dump(),
        "personas": [
            _persona(
                AgentName.SICHUAN_SPICY, "云吞粉丝", "cantonese", "只推荐广式云吞面"
            ),
            _persona(
                AgentName.CANTONESE_WELLNESS,
                "云吞本尊",
                "cantonese",
                "也推荐广式云吞面",
            ),
        ],
        "settings": {"min_rounds": 2, "max_rounds": 3, "early_stop": True},
    }
    sid = client.post("/api/v1/sessions", json=payload).json()["session_id"]
    # No personas/settings passed at debate time -> must use stored ones.
    body = client.post(f"/api/v1/sessions/{sid}/debate").json()
    assert len(body["messages"]) == 4  # converged at round 2
    assert body["personas"]["sichuan_spicy"] == "云吞粉丝"


# ---------------------------------------------------------------------------
# Early termination
# ---------------------------------------------------------------------------


def test_full_three_rounds_when_no_convergence() -> None:
    service = DebateService(in_memory=True)
    view = service.create_session(_prefs())
    final, events = service.run_debate(view.session_id)
    assert final.status.value == "SUCCESS"
    assert len(final.messages) == 6


def test_early_stop_when_both_name_same_dish() -> None:
    service = DebateService(in_memory=True)
    personas = [
        PersonaInput(
            agent=AgentName.SICHUAN_SPICY,
            label="云吞粉丝",
            style=PersonaStyle.CANTONESE,
            flavour="只推荐广式云吞面",
        ),
        PersonaInput(
            agent=AgentName.CANTONESE_WELLNESS,
            label="云吞本尊",
            style=PersonaStyle.CANTONESE,
            flavour="也推荐广式云吞面",
        ),
    ]
    settings = DebateSettings(min_rounds=2, max_rounds=3, early_stop=True)
    view = service.create_session(_prefs(taste="清淡"))
    final, events = service.run_debate(
        view.session_id, personas=personas, settings=settings
    )
    assert final.status.value == "SUCCESS"
    assert len(final.messages) == 4  # two chefs x two rounds
    kinds = [e.event for e in events]
    assert "report" in kinds
    # An info event announces the early stop.
    assert any(e.event == "info" and "达成一致" in str(e.data) for e in events)


def test_early_stop_disabled_runs_full_rounds() -> None:
    service = DebateService(in_memory=True)
    personas = [
        PersonaInput(
            agent=AgentName.SICHUAN_SPICY,
            label="云吞粉丝",
            style=PersonaStyle.CANTONESE,
            flavour="只推荐广式云吞面",
        ),
        PersonaInput(
            agent=AgentName.CANTONESE_WELLNESS,
            label="云吞本尊",
            style=PersonaStyle.CANTONESE,
            flavour="也推荐广式云吞面",
        ),
    ]
    settings = DebateSettings(min_rounds=1, max_rounds=3, early_stop=False)
    view = service.create_session(_prefs(taste="清淡"))
    final, _ = service.run_debate(view.session_id, personas=personas, settings=settings)
    assert len(final.messages) == 6  # early_stop off -> full three rounds


# ---------------------------------------------------------------------------
# Settings bounds
# ---------------------------------------------------------------------------


def test_settings_min_gt_max_rejected() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DebateSettings(min_rounds=3, max_rounds=2)


def test_settings_bounds_capped() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DebateSettings(min_rounds=0)
    with pytest.raises(ValidationError):
        DebateSettings(max_rounds=4)


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------


def test_menu_endpoint_returns_catalog() -> None:
    service = DebateService(in_memory=True)
    client = _api(service)
    response = client.get("/api/v1/menu")
    assert response.status_code == 200
    body = response.json()
    assert body["source_label"]
    assert len(body["items"]) >= 1
    required = {
        "name",
        "cuisine",
        "price_yuan",
        "spice_level",
        "rich_level",
        "heat_rating",
        "prep_minutes",
        "tags",
    }
    assert required <= set(body["items"][0])


def test_menu_loader_prefers_env_path(tmp_path) -> None:
    import os

    sample = {
        "source_label": "测试食堂",
        "items": [
            {
                "name": "测试回锅肉",
                "cuisine": "sichuan",
                "price_yuan": 13,
                "spice_level": 2,
                "rich_level": 2,
                "heat_rating": 2,
                "prep_minutes": 8,
                "tags": ["川"],
            }
        ],
    }
    menu_file = tmp_path / "menu.json"
    menu_file.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
    os.environ["FOODARENA_MENU_PATH"] = str(menu_file)
    try:
        catalog = load_menu()
        assert catalog.source_label == "测试食堂"
        assert catalog.items[0].name == "测试回锅肉"
        assert catalog.items[0].source == "sample"
    finally:
        os.environ.pop("FOODARENA_MENU_PATH", None)


def test_menu_loader_falls_back_on_broken_file(tmp_path) -> None:
    broken = tmp_path / "menu.json"
    broken.write_text("{ not json", encoding="utf-8")
    catalog = load_menu(str(broken))
    # Falls back to the built-in sample catalog.
    assert len(catalog.items) > 0
