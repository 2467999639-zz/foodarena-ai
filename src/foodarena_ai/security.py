"""Security boundaries for LLM prompts and structured logging."""

from __future__ import annotations

import logging
import re

# --------------------------------------------------------------------------
# Prompt-injection defence
# --------------------------------------------------------------------------

_USER_INPUT_START = "[用户偏好数据开始]"
_USER_INPUT_END = "[用户偏好数据结束]"

# Keywords that indicate an attempt to override the assistant's role or leak
# instructions/context. Such text is neutralised before it reaches a prompt.
_INJECTION_PATTERNS = re.compile(
    r"(?i)"
    r"(忽略.{0,8}(之前的|以上|先前|所有)?\s*(指令|指示|规则|设置|提示词)|"
    r"(从现在开始|接下来)(你是|扮演|忽略)|"
    r"(忘记|别管|不要管).{0,8}(指令|规则|角色|提示词|系统)|"
    r"(泄露|复述|告诉我).{0,8}(提示词|指令|密钥)|"
    r"(system|assistant)\s*[：:]\s*|"
    r"\b(ignore|disregard|forget)\b.{0,40}?\b(instructions|prompt|rules|context)\b|"
    r"\b(?:above|previous|all|prior)\b.{0,20}\binstructions\b|"
    r"\byou\s+are\s+now\s*[:=]|\bpretend\s+you\s+are\b|"
    r"\brepeat\b.{0,20}\b(instructions|prompt|system)\b)"
)

_CTRL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitise_user_text(text: str, *, max_length: int = 300) -> str:
    """Normalise and neutralise free-text user input.

    Control characters are removed, text is truncated to ``max_length`` and the
    result is wrapped in non-executable delimiters. Dangerous overrides such as
    "ignore previous instructions" are replaced with a neutral marker so they
    cannot act as instructions inside the prompt template.
    """
    cleaned = _CTRL_CHARS.sub("", text or "").strip()
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length] + "…"
    cleaned = _INJECTION_PATTERNS.sub("〔已过滤的内容〕", cleaned)
    return f"{_USER_INPUT_START}\n{cleaned}\n{_USER_INPUT_END}"


def looks_like_injection(text: str) -> bool:
    """Return True when free text attempts instruction/role override."""
    return bool(_INJECTION_PATTERNS.search(text or ""))


# --------------------------------------------------------------------------
# Structured, redacted logging
# --------------------------------------------------------------------------

_SECRET_PATTERNS = [
    # sk-... API keys (SiliconFlow style)
    re.compile(r"\bsk-[A-Za-z0-9_\-]{6,}\b"),
    # Bearer tokens
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{6,}\b", re.IGNORECASE),
    # email addresses
    re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
]


def redact_secrets(text: str) -> str:
    """Replace API keys, bearer tokens and emails with a fixed marker."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def bind_request_id() -> str:
    """Return a short request id for tracing (no randomness in logging calls)."""
    import secrets

    return secrets.token_hex(4)


class RequestFilter(logging.Filter):
    """Attach request_id, session_id and round to every log record."""

    def __init__(self, *, request_id: str | None = None) -> None:
        super().__init__()
        self.request_id = request_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(record, "request_id", None) or self.request_id
        record.session_id = getattr(record, "session_id", None)
        record.round = getattr(record, "round", None)
        return True


class StructuredFormatter(logging.Formatter):
    """Format records that may not carry the trace attributes.

    Third-party loggers (httpx, uvicorn, …) emit records that never pass
    through :class:`RequestFilter`, so the formatter substitutes a default
    rather than raising ``KeyError`` on a missing ``request_id``.
    """

    DEFAULTS = {"request_id": "-", "session_id": "-", "round": "-"}

    def format(self, record: logging.LogRecord) -> str:
        for key, default in self.DEFAULTS.items():
            if not hasattr(record, key):
                setattr(record, key, default)
        return super().format(record)
