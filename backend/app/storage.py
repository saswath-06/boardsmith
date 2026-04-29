from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from app.models import ArtifactInfo, JobSnapshot, PipelineEvent

ROOT = Path(__file__).resolve().parents[1]
GENERATED_ROOT = ROOT / "generated" / "jobs"


class JobRecord:
    def __init__(self, job_id: str, description: str) -> None:
        self.job_id = job_id
        self.description = description
        self.output_dir = GENERATED_ROOT / job_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.events: list[PipelineEvent] = []
        self.artifacts: dict[str, Path] = {}
        self.complete = False
        self.condition = asyncio.Condition()


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}

    def create(self, description: str) -> JobRecord:
        job_id = uuid.uuid4().hex[:12]
        record = JobRecord(job_id=job_id, description=description)
        self._jobs[job_id] = record
        return record

    def get(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    async def add_event(self, job_id: str, event: PipelineEvent) -> None:
        record = self._jobs[job_id]
        async with record.condition:
            record.events.append(event)
            record.condition.notify_all()

    async def finish(self, job_id: str) -> None:
        record = self._jobs[job_id]
        async with record.condition:
            record.complete = True
            record.condition.notify_all()

    def add_artifact(self, job_id: str, name: str, path: Path) -> None:
        self._jobs[job_id].artifacts[name] = path

    def snapshot(self, job_id: str) -> JobSnapshot | None:
        record = self.get(job_id)
        if not record:
            return None
        return JobSnapshot(
            job_id=record.job_id,
            complete=record.complete,
            events=record.events,
            artifacts=[
                ArtifactInfo(name=name, url=f"/api/jobs/{job_id}/artifact/{name}")
                for name in sorted(record.artifacts)
            ],
        )


STORE = JobStore()
