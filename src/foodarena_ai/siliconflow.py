"""Minimal SiliconFlow chat-completions client."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

LOGGER = logging.getLogger(__name__)


class SiliconFlowError(Exception):
    """Base error for SiliconFlow client failures."""


class SiliconFlowRequestError(SiliconFlowError):
    """Raised when a request cannot complete successfully."""


class SiliconFlowResponseError(SiliconFlowError):
    """Raised when a successful response violates the API contract."""


class SiliconFlowConfig(BaseModel):
    """Runtime configuration loaded from environment variables."""

    model_config = ConfigDict(frozen=True)

    base_url: str = Field(min_length=1)
    model: str = Field(min_length=1)
    api_key: SecretStr
    timeout_seconds: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=3, ge=0)
    backoff_seconds: float = Field(default=1.0, ge=0)

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        dotenv_path: str | os.PathLike[str] = ".env",
    ) -> SiliconFlowConfig:
        """Load required connection values from the environment or a .env file."""
        if environ is None:
            load_dotenv(dotenv_path=dotenv_path, override=False)
        values = os.environ if environ is None else environ
        required = (
            "SILICONFLOW_BASE_URL",
            "SILICONFLOW_MODEL",
            "SILICONFLOW_API_KEY",
        )
        missing = [name for name in required if not values.get(name, "").strip()]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"Missing required environment variables: {joined}")

        return cls(
            base_url=values["SILICONFLOW_BASE_URL"].strip(),
            model=values["SILICONFLOW_MODEL"].strip(),
            api_key=values["SILICONFLOW_API_KEY"].strip(),
        )


class ChatMessage(BaseModel):
    role: Literal["assistant"]
    content: str


class ChatChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str | None = None


class Usage(BaseModel):
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class ChatCompletionResponse(BaseModel):
    """Minimal validated subset of an OpenAI-compatible response."""

    id: str = Field(min_length=1)
    object: str = Field(min_length=1)
    created: int
    model: str = Field(min_length=1)
    choices: list[ChatChoice] = Field(min_length=1)
    usage: Usage | None = None


class SiliconFlowClient:
    """Call SiliconFlow with bounded retries for temporary failures."""

    _RETRYABLE_STATUS_CODES = frozenset({408, 425, 429})

    def __init__(
        self,
        config: SiliconFlowConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = config
        self._sleep = sleep
        self._client = httpx.Client(
            timeout=httpx.Timeout(config.timeout_seconds),
            transport=transport,
            headers={
                "Authorization": f"Bearer {config.api_key.get_secret_value()}",
                "Content-Type": "application/json",
            },
        )

    def __enter__(self) -> SiliconFlowClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
    ) -> ChatCompletionResponse:
        """Send one chat completion and validate the response."""
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": self._config.model,
            "messages": messages,
        }
        endpoint = f"{self._config.base_url.rstrip('/')}/chat/completions"

        for attempt in range(self._config.max_retries + 1):
            try:
                response = self._client.post(endpoint, json=payload)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= self._config.max_retries:
                    raise SiliconFlowRequestError(
                        "SiliconFlow request failed after retry limit"
                    ) from exc
                self._wait_before_retry(attempt, reason=type(exc).__name__)
                continue

            if response.status_code == httpx.codes.OK:
                return self._parse_response(response)

            if self._is_retryable(response.status_code):
                if attempt >= self._config.max_retries:
                    raise SiliconFlowRequestError(
                        "SiliconFlow request failed after retry limit "
                        f"(HTTP {response.status_code})"
                    )
                self._wait_before_retry(attempt, reason=f"HTTP {response.status_code}")
                continue

            raise SiliconFlowRequestError(
                f"SiliconFlow request failed (HTTP {response.status_code})"
            )

        raise AssertionError("retry loop ended unexpectedly")

    def _wait_before_retry(self, attempt: int, *, reason: str) -> None:
        delay = self._config.backoff_seconds * (2**attempt)
        LOGGER.warning(
            "Temporary SiliconFlow failure (%s); retrying in %.1f seconds",
            reason,
            delay,
        )
        self._sleep(delay)

    @classmethod
    def _is_retryable(cls, status_code: int) -> bool:
        return status_code in cls._RETRYABLE_STATUS_CODES or 500 <= status_code <= 599

    @staticmethod
    def _parse_response(response: httpx.Response) -> ChatCompletionResponse:
        try:
            return ChatCompletionResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise SiliconFlowResponseError(
                "SiliconFlow returned an invalid response"
            ) from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Test SiliconFlow connectivity")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Reply with exactly: foodarena connected",
        help="Prompt sent to the configured model",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run a real connectivity check using environment configuration."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _build_parser().parse_args(argv)

    try:
        config = SiliconFlowConfig.from_env()
        with SiliconFlowClient(config) as client:
            response = client.complete(args.prompt)
    except (ValueError, SiliconFlowError) as exc:
        LOGGER.error("Connectivity check failed: %s", exc)
        return 1

    print(response.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
