from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from app.models import JobCreateResponse, JobRequest, JobSnapshot
from app.pipeline import run_pipeline
from app.storage import STORE

load_dotenv()

app = FastAPI(title="Boardsmith API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


@app.get("/api/jobs/{job_id}", response_model=JobSnapshot)
async def get_job(job_id: str) -> JobSnapshot:
    snapshot = STORE.snapshot(job_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="job not found")
    return snapshot


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
    return StreamingResponse(_event_stream(job_id), media_type="text/event-stream")


@app.get("/api/jobs/{job_id}/artifact/{name}")
async def get_artifact(job_id: str, name: str) -> FileResponse:
    record = STORE.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="job not found")
    path = record.artifacts.get(name)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(path, filename=path.name)
