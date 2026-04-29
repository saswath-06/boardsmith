from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from app.auth import CurrentUser, CurrentUserFromQuery
from app.db import close_pool, init_pool
from app.models import (
    CircuitDesign,
    JobCreateResponse,
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


_ALLOWED_IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
_MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB; Gemini Vision handles up to ~20MB


@app.post("/api/jobs", response_model=JobCreateResponse)
async def create_job(
    user: CurrentUser,
    description: str = Form(""),
    image: UploadFile | None = File(None),
) -> JobCreateResponse:
    """Create a new job. Accepts text-only, image-only, or image+text.

    The endpoint is multipart/form-data so the optional image can be
    streamed without base64 overhead. At least one of ``description`` or
    ``image`` must be provided.
    """
    desc = (description or "").strip()
    image_bytes: bytes | None = None
    image_mime: str | None = None

    if image is not None and image.filename:
        if image.content_type not in _ALLOWED_IMAGE_MIMES:
            raise HTTPException(
                status_code=400,
                detail=f"unsupported image type: {image.content_type}",
            )
        image_bytes = await image.read()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="image file is empty")
        if len(image_bytes) > _MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"image too large (>{_MAX_IMAGE_BYTES // (1024 * 1024)} MB)",
            )
        image_mime = image.content_type

    if not desc and image_bytes is None:
        raise HTTPException(
            status_code=400,
            detail="provide a text description, an image, or both",
        )

    # Persisted description: use the text if present, otherwise a short
    # placeholder so the sidebar has something readable.
    persisted_desc = desc or f"Sketch upload ({image_mime or 'image'})"

    job = await STORE.create(user.user_id, persisted_desc)
    job.image_bytes = image_bytes
    job.image_mime = image_mime
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


@app.post("/api/jobs/{job_id}/publish")
async def publish_job(job_id: str, user: CurrentUser) -> dict[str, object]:
    """Mark a job as publicly shareable.

    The caller must own the job. Returns the relative share URL the
    frontend should copy to the clipboard.
    """
    try:
        await STORE.mark_public(user.user_id, job_id, True)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found") from None
    return {"public": True, "share_url": f"/p/{job_id}"}


@app.post("/api/jobs/{job_id}/unpublish")
async def unpublish_job(job_id: str, user: CurrentUser) -> dict[str, object]:
    """Revoke a public share link."""
    try:
        await STORE.mark_public(user.user_id, job_id, False)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found") from None
    return {"public": False}


@app.get("/api/public/jobs/{job_id}", response_model=JobSnapshot)
async def get_public_job(job_id: str) -> JobSnapshot:
    """Anonymous read-only access to a publicly-shared job.

    No auth required. The server only returns snapshots for jobs whose
    ``is_public`` flag is set; artifact URLs are stripped because the
    public viewer is intentionally view-only.
    """
    snapshot = await STORE.public_snapshot(job_id)
    if snapshot is None:
        raise HTTPException(
            status_code=404, detail="job not found or not shared"
        )
    return snapshot


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
