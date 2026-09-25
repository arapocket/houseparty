"""The app itself. Run it with:

    uv run uvicorn app.main:app --reload

Then open http://localhost:8000/docs for every endpoint, clickable.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.admin import mount_admin
from app.config import settings
from app.db import SessionFactory
from app.errors import RuleError
from app.routers import (
    auth,
    chat,
    discover,
    interests,
    invites,
    matches,
    parties,
    profile,
    safety,
)
from app.services.parties import complete_finished_parties

log = logging.getLogger("houseparty")


async def finish_parties_forever() -> None:
    """Every few minutes, mark parties that have ended as completed, which
    opens their reunion chat. Runs inside the web server so there is nothing
    else to deploy; move it to a real scheduler if we ever run several servers.
    """
    while True:
        try:
            async with SessionFactory() as session:
                finished = await complete_finished_parties(session)
                await session.commit()
            if finished:
                log.info("completed %d parties", len(finished))
        except Exception:
            # One bad run should not stop the loop for good.
            log.exception("finishing parties failed")
        await asyncio.sleep(settings.party_sweep_interval_seconds)


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(finish_parties_forever())
    yield
    task.cancel()


app = FastAPI(title="House Party", lifespan=lifespan)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.exception_handler(RuleError)
async def rule_error(_request: Request, error: RuleError) -> JSONResponse:
    """Services raise RuleError; this turns every one into the same JSON shape
    FastAPI uses for its own errors: {"detail": "..."}."""
    return JSONResponse(status_code=error.status_code, content={"detail": error.message})


@app.get("/healthz", tags=["meta"])
async def healthz() -> dict:
    return {"ok": True}


for module in (auth, profile, interests, discover, matches, parties, invites, chat, safety):
    app.include_router(module.router)

mount_admin(app)
