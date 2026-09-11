"""FastAPI application for the FoodArena campus food-debate game.

Serves the debate API under ``/api/v1`` and, when a production frontend build
exists in ``frontend/dist``, serves the SPA as static files.

Endpoints
---------
* ``POST   /api/v1/sessions``              create a session (201 + session_id)
* ``POST   /api/v1/sessions/{id}/debate``  run / finish the three-round debate
* ``GET    /api/v1/sessions/{id}``         current status / messages / report
* ``GET    /api/v1/sessions/{id}/events``  SSE stream (live, replayable)
* ``GET    /api/v1/sessions/{id}/report``  report only when SUCCESS (else 409)
* ``GET    /healthz``                      health probe for CI / containers
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import iterate_in_threadpool

from .config import settings
from .domain import (
    DebateStartRequest,
    ErrorResponse,
    MenuCatalog,
    SessionCreateRequest,
    SessionStatus,
    SessionSummary,
    SessionView,
)
from .menu_store import load_menu
from .security import StructuredFormatter
from .service import DebateService, SessionNotFound

LOGGER = logging.getLogger(__name__)

_service: DebateService | None = None


def get_service() -> DebateService:
    """Return the process-wide debate service (built lazily)."""
    global _service
    if _service is None:
        _service = DebateService(
            database_url=settings.database_url,
            default_provider=settings.default_provider,
            menu=load_menu(),
        )
    return _service


@asynccontextmanager
async def lifespan(_: FastAPI):
    handler = logging.StreamHandler()
    handler.setFormatter(
        StructuredFormatter(
            "%(asctime)s %(levelname)s %(name)s "
            "request=%(request_id)s session=%(session_id)s round=%(round)s %(message)s"
        )
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    yield


app = FastAPI(
    title="FoodArena AI API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/api/v1/menu", response_model=MenuCatalog)
def get_menu(service: DebateService = Depends(get_service)) -> MenuCatalog:
    """Return the validated menu currently used for recommendations."""
    return service.menu


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def _missing_session(exc: SessionNotFound) -> HTTPException:
    return HTTPException(
        status_code=404, detail=ErrorResponse(error=str(exc)).model_dump()
    )


@app.post(
    "/api/v1/sessions",
    response_model=SessionSummary,
    status_code=201,
)
def create_session(
    payload: SessionCreateRequest,
    service: DebateService = Depends(get_service),
) -> SessionSummary:
    preferences, personas, settings = payload.resolved()
    view = service.create_session(
        preferences, personas=personas or None, settings=settings
    )
    return SessionSummary(session_id=view.session_id, status=view.status)


@app.post("/api/v1/sessions/{session_id}/debate", response_model=SessionView)
def run_debate(
    session_id: UUID,
    payload: DebateStartRequest | None = None,
    service: DebateService = Depends(get_service),
) -> SessionView:
    """Run the debate (idempotent re-entry returns current state)."""
    personas = payload.personas if payload is not None else None
    settings = payload.settings if payload is not None else None
    provider = payload.provider if payload is not None else None
    try:
        view, _events = service.run_debate(
            session_id, provider=provider, personas=personas, settings=settings
        )
    except SessionNotFound as exc:
        raise _missing_session(exc) from exc
    return view


@app.get("/api/v1/sessions/{session_id}", response_model=SessionView)
def get_session(
    session_id: UUID,
    service: DebateService = Depends(get_service),
) -> SessionView:
    try:
        return service.get_session(session_id)
    except SessionNotFound as exc:
        raise _missing_session(exc) from exc


@app.get("/api/v1/sessions/{session_id}/events", response_class=StreamingResponse)
async def session_events(
    session_id: UUID,
    service: DebateService = Depends(get_service),
) -> StreamingResponse:
    """SSE stream of the debate.

    For a PENDING session the debate runs live and each event (status, round,
    message, report) is forwarded as soon as it is produced. For a session
    already started/finished the stored events are replayed so a reconnecting
    client rebuilds state without duplicate runs.
    """
    try:
        current = service.get_session(session_id)
        if current.status is SessionStatus.PENDING:
            steps = service.stream_debate(session_id)
        else:
            steps = None
    except SessionNotFound as exc:
        raise _missing_session(exc) from exc

    async def stream():
        if steps is not None:
            view: SessionView | None = None
            # Provider calls are deliberately synchronous, so advance the
            # generator in Starlette's worker pool.  Iterating it directly in
            # this async generator blocks the event loop during every model
            # request and lets browsers observe all SSE frames only at the end.
            async for _view, event in iterate_in_threadpool(steps):
                view = _view
                yield event.sse()
            status_label = view.status.value if view is not None else "FAILED"
        else:
            for event in service.replay_events(session_id):
                yield event.sse()
            status_label = current.status.value
        yield f"event: done\ndata: {status_label}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/v1/sessions/{session_id}/report")
def get_report(
    session_id: UUID,
    service: DebateService = Depends(get_service),
) -> dict:
    try:
        view = service.get_session(session_id)
    except SessionNotFound as exc:
        raise _missing_session(exc) from exc
    if view.status is not SessionStatus.SUCCESS or view.report is None:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(
                error="report not ready: session is not SUCCESS"
            ).model_dump(),
        )
    return view.report.model_dump()


# Optional SPA static hosting (used by the Docker single-image build).
if settings.static_dir:
    app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="spa")


def run() -> None:
    """Launch the API with uvicorn (``foodarena-api`` console script)."""
    import os

    import uvicorn

    port = int(os.getenv("FOODARENA_PORT", "8000"))
    uvicorn.run("foodarena_ai.main:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    run()
