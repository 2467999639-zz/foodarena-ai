"""Load a FoodArena menu from a JSON file.

Menu files follow the documented schema (see ``menu/sample_menu.json`` and
``README``). The store validates every item through Pydantic, falls back to
the built-in synthetic menu when no file is configured or the file is broken,
and exposes the source label so the UI can tell "示例" from "已加载真实菜单".
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .domain import BUILTIN_MENU, AgentSide, MenuCatalog, MenuItem, menu_from_items

LOGGER = logging.getLogger(__name__)

_DEFAULT_MENU_PATH = Path(__file__).resolve().parents[2] / "menu" / "sample_menu.json"


def _parse_cuisine(value: str) -> AgentSide:
    return AgentSide(value)


def _item_from_dict(raw: dict[str, Any]) -> MenuItem:
    """Map a raw menu row onto a MenuItem, tolerating friendly aliases."""
    cuisine_raw = raw.get("cuisine") or raw.get("side") or "sichuan"
    cuisine = AgentSide(cuisine_raw)
    known = {"cuisine": cuisine}
    for field, value in raw.items():
        if field in {"cuisine", "side"}:
            continue
        known[field] = value
    return MenuItem.model_validate(known)


def load_menu(path: str | None = None) -> MenuCatalog:
    """Load a menu from ``path`` (or the configured env path), else built-in.

    Invalid files degrade gracefully to the built-in menu with a warning; the
    service stays runnable for demos.
    """
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))
    configured = _default_menu_path()
    if configured not in candidates:
        candidates.append(configured)

    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("菜单文件无法解析 %s: %s，已回退内置样例", candidate, exc)
            continue
        try:
            items = [_item_from_dict(raw) for raw in data["items"]]
            return menu_from_items(
                items,
                source_label=data.get("source_label", "真实菜单"),
            )
        except (KeyError, TypeError, ValidationError, ValueError) as exc:
            LOGGER.warning("菜单文件校验失败 %s: %s，已回退内置样例", candidate, exc)
            continue
    return BUILTIN_MENU


def _default_menu_path() -> Path:
    import os

    env = os.getenv("FOODARENA_MENU_PATH", "")
    if env:
        return Path(env)
    return _DEFAULT_MENU_PATH
