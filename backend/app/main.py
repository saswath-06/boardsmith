from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

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
    """CORS origins from env, comma-separated. Defaults to localhost dev hosts.

    Use ``FRONTEND_URL`` in production (e.g. ``https://boardsmith.up.railway.app``).
    Set ``CORS_ALLOW_ALL=1`` for the wide-open dev fallback.
    """
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


app = FastAPI(title="Boardsmith API", version="0.1.0")
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
async def create_job(request: JobRequest) -> JobCreateResponse:
    job = STORE.create(request.description)
    asyncio.create_task(run_pipeline(job))
    return JobCreateResponse(job_id=job.job_id)


@app.get("/api/jobs", response_model=list[JobSummary])
async def list_jobs() -> list[JobSummary]:
    """All jobs in this process, newest first. Used by the sidebar."""
    return STORE.summaries()


@app.get("/api/jobs/{job_id}", response_model=JobSnapshot)
async def get_job(job_id: str) -> JobSnapshot:
    snapshot = STORE.snapshot(job_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="job not found")
    return snapshot


@app.get("/api/jobs/{job_id}/lineage", response_model=list[LineageEntry])
async def get_lineage(job_id: str) -> list[LineageEntry]:
    chain = STORE.lineage(job_id)
    if chain is None:
        raise HTTPException(status_code=404, detail="job not found")
    return chain


@app.post("/api/jobs/{parent_id}/refine", response_model=JobCreateResponse)
async def refine_job(parent_id: str, request: RefineRequest) -> JobCreateResponse:
    parent = STORE.get(parent_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="parent job not found")
    if not parent.complete:
        raise HTTPException(status_code=409, detail="parent job is not complete yet")
    design_path = parent.output_dir / "circuit.json"
    if not design_path.exists():
        raise HTTPException(status_code=410, detail="parent design no longer available")

    try:
        parent_design = CircuitDesign.model_validate(
            json.loads(design_path.read_text(encoding="utf-8"))
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"failed to load parent design: {exc}")

    try:
        child = STORE.create_revision(parent_id, request.instruction)
    except (KeyError, ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    asyncio.create_task(run_refinement_pipeline(child, parent_design))
    return JobCreateResponse(job_id=child.job_id)


async def _event_stream(job_id: str) -> AsyncIterator[str]:
    record = STORE.get(job_id)
    if not record:
        yield "event: error\ndata: {\"message\":\"job not found\"}\n\n"
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
async def job_events(job_id: str) -> StreamingResponse:
    if not STORE.get(job_id):
        raise HTTPException(status_code=404, detail="job not found")
    # Headers force the upstream proxy (Railway/Caddy/nginx) to flush every
    # event immediately instead of buffering until the response closes.
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
async def get_artifact(job_id: str, name: str) -> FileResponse:
    record = STORE.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="job not found")
    path = record.artifacts.get(name)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(path, filename=path.name)
