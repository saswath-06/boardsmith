from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from app.auth import CurrentUser, CurrentUserFromQuery
from app.db import close_pool, init_pool
from app.models import (
    CircuitDesign,
    JobCreateResponse,
    JobRequest,
    JobSnapshot,
    JobSummary,
    LineageEntry,
    RefineRequest,
)
from app.pipeline import run_pipeline, run_refinement_pipeline
from app.storage import STORE

load_dotenv()


def _cors_origins() -> list[str]:
    """CORS origins from env, comma-separated. Defaults to localhost dev hosts."""
    if os.getenv("CORS_ALLOW_ALL") == "1":
        return ["*"]
    raw = os.getenv("FRONTEND_URL") or os.getenv("CORS_ORIGINS") or ""
    explicit = [o.strip() for o in raw.split(",") if o.strip()]
    defaults = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]
    return explicit + defaults if explicit else defaults


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(title="Boardsmith API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/api/jobs", response_model=JobCreateResponse)
async def create_job(request: JobRequest, user: CurrentUser) -> JobCreateResponse:
    job = await STORE.create(user.user_id, request.description)
    asyncio.create_task(run_pipeline(job))
    return JobCreateResponse(job_id=job.job_id)


@app.get("/api/jobs", response_model=list[JobSummary])
async def list_jobs(user: CurrentUser) -> list[JobSummary]:
    return await STORE.summaries_for_user(user.user_id)


@app.get("/api/jobs/{job_id}", response_model=JobSnapshot)
async def get_job(job_id: str, user: CurrentUser) -> JobSnapshot:
    snapshot = await STORE.snapshot_for_user(user.user_id, job_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="job not found")
    return snapshot


@app.get("/api/jobs/{job_id}/lineage", response_model=list[LineageEntry])
async def get_lineage(job_id: str, user: CurrentUser) -> list[LineageEntry]:
    chain = await STORE.lineage_for_user(user.user_id, job_id)
    if chain is None:
        raise HTTPException(status_code=404, detail="job not found")
    return chain


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str, user: CurrentUser) -> dict[str, list[str]]:
    """Delete a job and all its descendant revisions.

    Returns ``{"deleted": [job_id, ...]}`` so the frontend knows which IDs
    to drop from the sidebar (the cascade may include child revisions).
    """
    try:
        deleted = await STORE.delete_for_user(user.user_id, job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found") from None
    return {"deleted": deleted}


@app.post("/api/jobs/{parent_id}/refine", response_model=JobCreateResponse)
async def refine_job(
    parent_id: str, request: RefineRequest, user: CurrentUser
) -> JobCreateResponse:
    try:
        design_dict = await STORE.get_parent_design(user.user_id, parent_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="parent job not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None

    try:
        parent_design = CircuitDesign.model_validate(design_dict)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"failed to load parent design: {exc}")

    try:
        child = await STORE.create_revision(user.user_id, parent_id, request.instruction)
    except (KeyError, ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    asyncio.create_task(run_refinement_pipeline(child, parent_design))
    return JobCreateResponse(job_id=child.job_id)


async def _event_stream(job_id: str) -> AsyncIterator[str]:
    record = STORE.get(job_id)
    if not record:
        # Job already completed and got evicted from memory — replay events
        # from Postgres so a late subscriber still gets the full log.
        yield "event: error\ndata: {\"message\":\"job not active — fetch /api/jobs/{id} for snapshot\"}\n\n"
        return
    yield "retry: 1000\n\n"
    index = 0
    while True:
        async with record.condition:
            while index >= len(record.events) and not record.complete:
                await record.condition.wait()
            events = record.events[index:]
            index = len(record.events)
            complete = record.complete
        for event in events:
            payload = json.dumps(event.model_dump(mode="json"))
            yield f"data: {payload}\n\n"
        if complete and index >= len(record.events):
            break


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str, user: CurrentUserFromQuery) -> StreamingResponse:
    if not await STORE.owns(user.user_id, job_id):
        raise HTTPException(status_code=404, detail="job not found")
    return StreamingResponse(
        _event_stream(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/jobs/{job_id}/artifact/{name}")
async def get_artifact(
    job_id: str, name: str, user: CurrentUserFromQuery
) -> FileResponse:
    # Uses CurrentUserFromQuery so browser <a download> links can pass
    # ?token=<jwt> instead of an Authorization header.
    path = await STORE.artifact_path_for_user(user.user_id, job_id, name)
    if path is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(path, filename=path.name)
