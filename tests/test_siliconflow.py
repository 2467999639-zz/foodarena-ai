from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest

from foodarena_ai.siliconflow import (
    SiliconFlowClient,
    SiliconFlowConfig,
    SiliconFlowRequestError,
    SiliconFlowResponseError,
)

API_KEY = "secret-test-key-that-must-not-be-logged"


def config(**overrides: object) -> SiliconFlowConfig:
    values: dict[str, object] = {
        "base_url": "https://api.siliconflow.example/v1",
        "model": "deepseek-ai/DeepSeek-V4-Flash",
        "api_key": API_KEY,
        "backoff_seconds": 1,
    }
    values.update(overrides)
    return SiliconFlowConfig.model_validate(values)


def successful_payload() -> dict[str, object]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1_788_192_000,
        "model": "deepseek-ai/DeepSeek-V4-Flash",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "foodarena connected",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "total_tokens": 12,
        },
    }


def test_config_reads_required_environment_values() -> None:
    result = SiliconFlowConfig.from_env(
        {
            "SILICONFLOW_BASE_URL": "https://api.siliconflow.example/v1",
            "SILICONFLOW_MODEL": "deepseek-ai/DeepSeek-V4-Flash",
            "SILICONFLOW_API_KEY": API_KEY,
        }
    )

    assert result.timeout_seconds == 30
    assert result.max_retries == 3
    assert result.api_key.get_secret_value() == API_KEY


def test_config_reports_missing_environment_values_without_secrets() -> None:
    with pytest.raises(ValueError, match="SILICONFLOW_MODEL") as error:
        SiliconFlowConfig.from_env(
            {
                "SILICONFLOW_BASE_URL": "https://example.test/v1",
                "SILICONFLOW_API_KEY": API_KEY,
            }
        )

    assert API_KEY not in str(error.value)


def test_config_loads_dotenv_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "SILICONFLOW_BASE_URL=https://api.siliconflow.example/v1\n"
        "SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V4-Flash\n"
        f"SILICONFLOW_API_KEY={API_KEY}\n",
        encoding="utf-8",
    )
    for name in (
        "SILICONFLOW_BASE_URL",
        "SILICONFLOW_MODEL",
        "SILICONFLOW_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    result = SiliconFlowConfig.from_env(dotenv_path=dotenv_path)

    assert result.model == "deepseek-ai/DeepSeek-V4-Flash"
    assert result.api_key.get_secret_value() == API_KEY


def test_success_returns_validated_schema_and_uses_expected_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.siliconflow.example/v1/chat/completions"
        assert request.headers["Authorization"] == f"Bearer {API_KEY}"
        assert request.extensions["timeout"] == {
            "connect": 30.0,
            "read": 30.0,
            "write": 30.0,
            "pool": 30.0,
        }
        body = json.loads(request.content)
        assert body == {
            "model": "deepseek-ai/DeepSeek-V4-Flash",
            "messages": [{"role": "user", "content": "hello"}],
        }
        return httpx.Response(200, json=successful_payload())

    with SiliconFlowClient(config(), transport=httpx.MockTransport(handler)) as client:
        result = client.complete("hello")

    assert result.choices[0].message.content == "foodarena connected"


def test_429_retries_with_exponential_backoff() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 4:
            return httpx.Response(429, request=request)
        return httpx.Response(200, json=successful_payload(), request=request)

    with SiliconFlowClient(
        config(), transport=httpx.MockTransport(handler), sleep=delays.append
    ) as client:
        result = client.complete("hello")

    assert result.id == "chatcmpl-test"
    assert attempts == 4
    assert delays == [1, 2, 4]


def test_temporary_transport_error_is_retried() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("temporary timeout", request=request)
        return httpx.Response(200, json=successful_payload(), request=request)

    with SiliconFlowClient(
        config(), transport=httpx.MockTransport(handler), sleep=delays.append
    ) as client:
        client.complete("hello")

    assert attempts == 2
    assert delays == [1]


def test_retry_limit_is_three_retries() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, request=request)

    with (
        SiliconFlowClient(
            config(), transport=httpx.MockTransport(handler), sleep=delays.append
        ) as client,
        pytest.raises(SiliconFlowRequestError, match="retry limit"),
    ):
        client.complete("hello")

    assert attempts == 4
    assert delays == [1, 2, 4]


def test_non_retryable_client_error_fails_immediately() -> None:
    delays: list[float] = []
    transport = httpx.MockTransport(
        lambda request: httpx.Response(401, request=request)
    )

    with (
        SiliconFlowClient(config(), transport=transport, sleep=delays.append) as client,
        pytest.raises(SiliconFlowRequestError, match="HTTP 401"),
    ):
        client.complete("hello")

    assert delays == []


def test_invalid_success_response_fails_schema_validation() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"id": "incomplete"}, request=request)
    )

    with (
        SiliconFlowClient(config(), transport=transport) as client,
        pytest.raises(SiliconFlowResponseError, match="invalid response"),
    ):
        client.complete("hello")


def test_logs_do_not_contain_api_key(caplog: pytest.LogCaptureFixture) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(503, request=request)
    )
    caplog.set_level(logging.WARNING)

    with (
        SiliconFlowClient(
            config(max_retries=1), transport=transport, sleep=lambda _: None
        ) as client,
        pytest.raises(SiliconFlowRequestError),
    ):
        client.complete("hello")

    assert API_KEY not in caplog.text
