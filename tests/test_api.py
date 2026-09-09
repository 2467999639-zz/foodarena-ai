"""HTTP-level tests for the FastAPI endpoints (TECH02/US01/US03 acceptance)."""

from __future__ import annotations

VALID_PAYLOAD = {
    "taste": "麻辣",
    "budget_yuan": 15,
    "weather": "rainy",
    "companions": 2,
}


def test_create_session_returns_201_with_id(client) -> None:
    response = client.post("/api/v1/sessions", json=VALID_PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PENDING"
    assert len(body["session_id"]) == 36


def test_invalid_preferences_return_422_with_structured_error(client) -> None:
    response = client.post(
        "/api/v1/sessions",
        json={**VALID_PAYLOAD, "budget_yuan": 0, "companions": 40},
    )
    assert response.status_code == 422
    payload = response.json()
    # FastAPI default validation detail lists field-level errors
    assert "detail" in payload


def test_debate_returns_success_view_and_six_messages(client) -> None:
    session_id = client.post("/api/v1/sessions", json=VALID_PAYLOAD).json()[
        "session_id"
    ]
    response = client.post(f"/api/v1/sessions/{session_id}/debate")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert len(body["messages"]) == 6
    assert body["report"]["dish"]
    assert set(body["report"]["score_breakdown"]) == {
        "taste",
        "budget",
        "weather",
        "debate",
    }


def test_duplicate_debate_start_is_idempotent(client) -> None:
    session_id = client.post("/api/v1/sessions", json=VALID_PAYLOAD).json()[
        "session_id"
    ]
    first = client.post(f"/api/v1/sessions/{session_id}/debate").json()
    second = client.post(f"/api/v1/sessions/{session_id}/debate").json()
    assert second["status"] == "SUCCESS"
    assert len(second["messages"]) == 6
    assert len(first["messages"]) == len(second["messages"])


def test_get_session_reflects_pending_then_success(client) -> None:
    session_id = client.post("/api/v1/sessions", json=VALID_PAYLOAD).json()[
        "session_id"
    ]
    pending = client.get(f"/api/v1/sessions/{session_id}").json()
    assert pending["status"] == "PENDING"
    client.post(f"/api/v1/sessions/{session_id}/debate")
    done = client.get(f"/api/v1/sessions/{session_id}").json()
    assert done["status"] == "SUCCESS"


def test_report_gated_until_success(client) -> None:
    session_id = client.post("/api/v1/sessions", json=VALID_PAYLOAD).json()[
        "session_id"
    ]
    # not started -> 409
    assert client.get(f"/api/v1/sessions/{session_id}/report").status_code == 409
    client.post(f"/api/v1/sessions/{session_id}/debate")
    response = client.get(f"/api/v1/sessions/{session_id}/report")
    assert response.status_code == 200
    assert "dish" in response.json()


def test_report_again_is_readable_and_identical(client) -> None:
    session_id = client.post("/api/v1/sessions", json=VALID_PAYLOAD).json()[
        "session_id"
    ]
    client.post(f"/api/v1/sessions/{session_id}/debate")
    first = client.get(f"/api/v1/sessions/{session_id}/report").json()
    second = client.get(f"/api/v1/sessions/{session_id}/report").json()
    assert first == second


def test_unknown_session_returns_404(client) -> None:
    missing = "00000000-0000-0000-0000-000000000001"
    assert client.get(f"/api/v1/sessions/{missing}").status_code == 404
    assert client.post(f"/api/v1/sessions/{missing}/debate").status_code == 404
    assert client.get(f"/api/v1/sessions/{missing}/report").status_code == 404


def test_events_endpoint_streams_sse_events(client) -> None:
    session_id = client.post("/api/v1/sessions", json=VALID_PAYLOAD).json()[
        "session_id"
    ]
    with client.stream("GET", f"/api/v1/sessions/{session_id}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())
    assert "event: status" in body
    assert "event: message" in body
    assert "event: report" in body
    assert "SUCCESS" in body


def test_events_replay_for_finished_session_has_exactly_six_messages(client) -> None:
    session_id = client.post("/api/v1/sessions", json=VALID_PAYLOAD).json()[
        "session_id"
    ]
    client.post(f"/api/v1/sessions/{session_id}/debate")
    with client.stream("GET", f"/api/v1/sessions/{session_id}/events") as response:
        body = "".join(response.iter_text())
    assert body.count("event: message") == 6
    assert "event: done" in body


def test_healthz(client) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
