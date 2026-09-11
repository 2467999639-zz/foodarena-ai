"""Contract and validation tests for the domain models (QA01/SEC01 style)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from foodarena_ai.domain import (
    AgentMessage,
    AgentName,
    DebateReport,
    PreferenceInput,
    ProviderMode,
    SessionStatus,
    SessionView,
    Weather,
)

VALID = {
    "taste": "麻辣",
    "budget_yuan": 15,
    "weather": "rainy",
    "companions": 2,
}


def test_valid_preference_input_parses_enum_weather() -> None:
    pref = PreferenceInput.model_validate(VALID)
    assert pref.weather is Weather.RAINY
    assert pref.taste == "麻辣"


@pytest.mark.parametrize(
    "field,value",
    [
        ("taste", ""),  # empty taste
        ("budget_yuan", 0),  # budget too low
        ("budget_yuan", 201),  # budget too high
        ("companions", 0),  # no companions
        ("companions", 21),  # too many companions
        ("weather", "snowy"),  # unknown enum
    ],
)
def test_invalid_preference_field_is_rejected(field: str, value: object) -> None:
    payload = dict(VALID)
    payload[field] = value
    with pytest.raises(ValidationError):
        PreferenceInput.model_validate(payload)


def test_whitespace_only_taste_is_rejected() -> None:
    payload = dict(VALID, taste="   ")
    with pytest.raises(ValidationError):
        PreferenceInput.model_validate(payload)


def test_overlong_taste_is_rejected() -> None:
    payload = dict(VALID, taste="辣" * 61)
    with pytest.raises(ValidationError):
        PreferenceInput.model_validate(payload)


def test_message_contract_fields_and_round_bounds() -> None:
    msg = AgentMessage(
        round=1,
        agent=AgentName.SICHUAN_SPICY,
        argument="来一碗麻辣小面",
        evidence="¥10 校内窗口",
    )
    dumped = msg.model_dump()
    assert set(dumped) == {"round", "agent", "argument", "evidence"}
    with pytest.raises(ValidationError):
        AgentMessage(
            round=4,
            agent=AgentName.CANTONESE_WELLNESS,
            argument="x",
            evidence="y",
        )


def test_report_contract_bounds_confidence_and_breakdown() -> None:
    report = DebateReport(
        dish="川味小面",
        cuisine="sichuan",
        reason="预算内且暖胃",
        confidence=0.9,
        score_breakdown={"taste": 4.5, "budget": 5.0, "weather": 4.0, "debate": 3.5},
    )
    assert report.confidence == 0.9
    assert set(report.score_breakdown) == {"taste", "budget", "weather", "debate"}
    # confidence outside [0, 1] is rejected by the schema
    with pytest.raises(ValidationError):
        DebateReport(
            dish="x",
            cuisine="sichuan",
            reason="y",
            confidence=1.2,
            score_breakdown={},
        )


def test_provider_mode_and_status_enums_are_json_friendly() -> None:
    assert SessionStatus.SUCCESS.value == "SUCCESS"
    assert ProviderMode.MOCK.value == "mock"


def test_session_view_defaults_to_empty() -> None:
    view = SessionView(
        session_id="12345678-1234-5678-1234-567812345678", status=SessionStatus.PENDING
    )
    assert view.messages == []
    assert view.report is None
