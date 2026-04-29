from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path

from app.models import (
    ArtifactInfo,
    JobSnapshot,
    JobSummary,
    LineageEntry,
    PipelineEvent,
)

ROOT = Path(__file__).resolve().parents[1]
GENERATED_ROOT = ROOT / "generated" / "jobs"


class JobRecord:
    def __init__(
        self,
        job_id: str,
        description: str,
        *,
        parent_job_id: str | None = None,
        instruction: str | None = None,
        revision: int = 0,
    ) -> None:
        self.job_id = job_id
        self.description = description
        self.parent_job_id = parent_job_id
        self.instruction = instruction
        self.revision = revision
        self.created_at = time.time()
        self.output_dir = GENERATED_ROOT / job_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.events: list[PipelineEvent] = []
        self.artifacts: dict[str, Path] = {}
        self.complete = False
        self.condition = asyncio.Condition()

    def _design_counts(self) -> tuple[int, int]:
        """Read the persisted circuit JSON (if any) for sidebar component/net counts."""
        path = self.output_dir / "circuit.json"
        if not path.exists():
            return (0, 0)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return (0, 0)
        return (
            len(data.get("components", []) or []),
            len(data.get("nets", []) or []),
        )

    def title(self) -> str:
        """Sidebar/lineage label: instruction for revisions, description for roots."""
        if self.revision and self.instruction:
            return self.instruction
        return self.description or self.job_id


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}

    def create(self, description: str) -> JobRecord:
        job_id = uuid.uuid4().hex[:12]
        record = JobRecord(job_id=job_id, description=description)
        self._jobs[job_id] = record
        return record

    def create_revision(self, parent_job_id: str, instruction: str) -> JobRecord:
        parent = self.get(parent_job_id)
        if parent is None:
            raise KeyError(f"parent job {parent_job_id} not found")
        if not parent.complete:
            raise ValueError("parent job is not complete yet")
        if not (parent.output_dir / "circuit.json").exists():
            raise FileNotFoundError("parent design circuit.json missing on disk")
        job_id = uuid.uuid4().hex[:12]
        record = JobRecord(
            job_id=job_id,
            description=instruction,
            parent_job_id=parent_job_id,
            instruction=instruction,
            revision=parent.revision + 1,
        )
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
            parent_job_id=record.parent_job_id,
            instruction=record.instruction,
            revision=record.revision,
            description=record.description,
            created_at=record.created_at,
        )

    def summaries(self) -> list[JobSummary]:
        rows: list[JobSummary] = []
        for record in self._jobs.values():
            comps, nets = record._design_counts()
            rows.append(
                JobSummary(
                    job_id=record.job_id,
                    description=record.description,
                    instruction=record.instruction,
                    parent_job_id=record.parent_job_id,
                    revision=record.revision,
                    complete=record.complete,
                    components=comps,
                    nets=nets,
                    created_at=record.created_at,
                )
            )
        rows.sort(key=lambda r: r.created_at, reverse=True)
        return rows

    def lineage(self, job_id: str) -> list[LineageEntry] | None:
        leaf = self.get(job_id)
        if leaf is None:
            return None
        chain: list[JobRecord] = []
        cursor: JobRecord | None = leaf
        seen: set[str] = set()
        while cursor is not None and cursor.job_id not in seen:
            chain.append(cursor)
            seen.add(cursor.job_id)
            if cursor.parent_job_id is None:
                break
            cursor = self.get(cursor.parent_job_id)
        chain.reverse()
        return [
            LineageEntry(
                job_id=r.job_id,
                revision=r.revision,
                title=r.title(),
                complete=r.complete,
            )
            for r in chain
        ]


STORE = JobStore()
