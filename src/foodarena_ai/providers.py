"""Construct the real (SiliconFlow) provider from environment configuration.

Kept separate from ``service`` so the debate service stays free of HTTP
concerns and the app can decide at runtime whether a real API key is present.
"""

from __future__ import annotations

from .service import DebateProviderError, SiliconFlowChefProvider


def build_real_provider() -> SiliconFlowChefProvider:
    """Build a SiliconFlow-backed provider from env vars.

    Raises ``DebateProviderError`` when connection values are missing so the
    caller can degrade to FAILED rather than crash.
    """
    from .siliconflow import SiliconFlowClient, SiliconFlowConfig

    try:
        config = SiliconFlowConfig.from_env()
    except ValueError as exc:  # missing required variables
        raise DebateProviderError(str(exc)) from exc

    client = SiliconFlowClient(config)

    def call(prompt: str, system_prompt: str | None) -> str:
        try:
            response = client.complete(prompt, system_prompt=system_prompt)
        except Exception:
            client.close()
            raise
        content = response.choices[0].message.content if response.choices else ""
        return content or ""

    return SiliconFlowChefProvider(client, call=call)
