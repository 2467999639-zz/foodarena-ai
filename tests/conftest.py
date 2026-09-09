"""Shared pytest fixtures for FoodArena tests (no external network)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from foodarena_ai.domain import PreferenceInput, Weather
from foodarena_ai.service import DebateService

WEATHER = Weather


@pytest.fixture()
def preferences() -> PreferenceInput:
    """A representative valid preference set used across tests."""
    return PreferenceInput(
        taste="麻辣",
        budget_yuan=15,
        weather=Weather.RAINY,
        companions=2,
    )


@pytest.fixture()
def service() -> DebateService:
    """A debate service backed by a fresh in-memory SQLite database."""
    return DebateService(in_memory=True)


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    """An API test client wired to an in-memory service."""
    import foodarena_ai.main as main

    in_memory_service = DebateService(in_memory=True)

    def override():
        return in_memory_service

    main.app.dependency_overrides[main.get_service] = override
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()
