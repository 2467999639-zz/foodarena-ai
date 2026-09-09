"""Tests for the real (SiliconFlow) provider: parsing, schema repair, bounding.

No network calls are made: ``call`` is injected, so only the JSON parsing and
contract-enforcement layer is exercised.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from foodarena_ai.domain import (
    AgentName,
    PreferenceInput,
    Weather,
)
from foodarena_ai.service import (
    DebateContext,
    DebateProviderError,
    SchemaRepairError,
    SiliconFlowChefProvider,
)

REQ_ID = "test-request"
SID = uuid4()


def _provider(output: str) -> SiliconFlowChefProvider:
    def call(prompt: str, system_prompt: str | None) -> str:
        return output

    return SiliconFlowChefProvider(client=None, call=call)  # type: ignore[arg-type]


def _ctx(agent: AgentName = AgentName.SICHUAN_SPICY) -> DebateContext:
    return DebateContext(
        preferences=PreferenceInput(
            taste="麻辣", budget_yuan=15, weather=Weather.RAINY, companions=2
        ),
        user_block="data",
        round_number=1,
        agent=agent,
        previous_argument=None,
    )


def test_chef_argument_parses_clean_json() -> None:
    provider = _provider('{"argument":"推荐口水鸡","evidence":"¥18 下饭"}')
    message = provider.argument(_ctx(), session_id=SID, request_id=REQ_ID)
    assert message.argument == "推荐口水鸡"
    assert message.evidence == "¥18 下饭"
    assert message.round == 1
    assert message.agent is AgentName.SICHUAN_SPICY


def test_chef_argument_strips_markdown_fences() -> None:
    raw = '```json\n{"argument":"a","evidence":"b"}\n```'
    message = _provider(raw).argument(_ctx(), session_id=SID, request_id=REQ_ID)
    assert message.argument == "a"


def test_chef_argument_trims_surrounding_noise_to_braces() -> None:
    raw = '好的，我的回答如下：{"argument":"麻辣小面","evidence":"窗口现做"}。完毕'
    message = _provider(raw).argument(_ctx(), session_id=SID, request_id=REQ_ID)
    assert message.argument == "麻辣小面"


def test_missing_fields_raise_provider_error() -> None:
    with pytest.raises(DebateProviderError, match="missing argument"):
        _provider('{"argument":""}').argument(_ctx(), session_id=SID, request_id=REQ_ID)


def test_non_json_output_raises_schema_repair_error() -> None:
    with pytest.raises(SchemaRepairError):
        _provider("完全不是 JSON 的文本").argument(
            _ctx(), session_id=SID, request_id=REQ_ID
        )


def test_judge_report_clamps_confidence_and_scores() -> None:
    raw = (
        '{"dish":"川味小面","cuisine":"sichuan","reason":"预算内暖胃",'
        '"confidence":3.5,"score_breakdown":{"taste":9,"budget":5,"weather":2,"debate":1}}'
    )
    report = _provider(raw).report(
        preferences=_ctx().preferences,
        transcript="t",
        session_id=SID,
        request_id=REQ_ID,
    )
    assert report.confidence == 1.0  # clamped from 3.5
    assert report.score_breakdown["taste"] == 5.0  # clamped from 9
    assert report.score_breakdown["budget"] == 5.0


def test_judge_invalid_cuisine_falls_back_to_sichuan() -> None:
    raw = (
        '{"dish":"x","cuisine":"kebab","reason":"y","confidence":0.5,'
        '"score_breakdown":{}}'
    )
    report = _provider(raw).report(
        preferences=_ctx().preferences,
        transcript="t",
        session_id=SID,
        request_id=REQ_ID,
    )
    assert report.cuisine == "sichuan"


def test_empty_model_output_raises() -> None:
    with pytest.raises(DebateProviderError, match="empty"):
        _provider("   ").argument(_ctx(), session_id=SID, request_id=REQ_ID)
