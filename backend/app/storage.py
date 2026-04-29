"""Job storage: in-memory hot cache + Postgres durable record.

Active jobs (those currently streaming SSE events) live in an in-memory
dict so the ``asyncio.Condition`` machinery for SSE works. After a job
completes — or any time we need to load a job that's no longer in
memory — we read from Postgres.

All queries are scoped by ``user_id``: a user can never read or refine
another user's job.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any

from app.db import execute, fetch_all, fetch_one
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
    """In-memory live state for an active or recently-completed job."""

    def __init__(
        self,
        job_id: str,
        user_id: str,
        description: str,
        *,
        parent_job_id: str | None = None,
        instruction: str | None = None,
        revision: int = 0,
    ) -> None:
        self.job_id = job_id
        self.user_id = user_id
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

    def title(self) -> str:
        if self.revision and self.instruction:
            return self.instruction
        return self.description or self.job_id


def _row_to_summary(row: Any) -> JobSummary:
    design = row["design_json"] or {}
    return JobSummary(
        job_id=row["job_id"],
        description=row["description"],
        instruction=row["instruction"],
        parent_job_id=row["parent_job_id"],
        revision=row["revision"],
        complete=row["complete"],
        components=len(design.get("components", []) or []) if isinstance(design, dict) else 0,
        nets=len(design.get("nets", []) or []) if isinstance(design, dict) else 0,
        created_at=row["created_at"].timestamp(),
    )


def _row_to_snapshot(row: Any, artifacts: dict[str, Path]) -> JobSnapshot:
    raw_events = row["events_json"] or []
    if isinstance(raw_events, str):
        raw_events = json.loads(raw_events)
    events = [PipelineEvent.model_validate(e) for e in raw_events]
    return JobSnapshot(
        job_id=row["job_id"],
        complete=row["complete"],
        events=events,
        artifacts=[
            ArtifactInfo(name=name, url=f"/api/jobs/{row['job_id']}/artifact/{name}")
            for name in sorted(artifacts.keys())
        ],
        parent_job_id=row["parent_job_id"],
        instruction=row["instruction"],
        revision=row["revision"],
        description=row["description"],
        created_at=row["created_at"].timestamp(),
    )


class JobStore:
    """Hot cache + durable storage for jobs.

    Active jobs live in ``self._jobs`` so the streaming machinery
    (``asyncio.Condition``) works without round-trips to Postgres.
    Completed jobs are evicted from the cache after a brief grace window
    when the next read against Postgres covers them.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}

    # ── creation ─────────────────────────────────────────────────────────

    async def create(self, user_id: str, description: str) -> JobRecord:
        job_id = uuid.uuid4().hex[:12]
        record = JobRecord(job_id=job_id, user_id=user_id, description=description)
        await execute(
            """
            INSERT INTO jobs (job_id, user_id, description, revision)
            VALUES ($1, $2, $3, 0)
            """,
            job_id,
            user_id,
            description,
        )
        self._jobs[job_id] = record
        return record

    async def create_revision(
        self, user_id: str, parent_job_id: str, instruction: str
    ) -> JobRecord:
        parent_row = await fetch_one(
            """
            SELECT job_id, user_id, revision, complete, design_json
            FROM jobs
            WHERE job_id = $1 AND user_id = $2
            """,
            parent_job_id,
            user_id,
        )
        if parent_row is None:
            raise KeyError(f"parent job {parent_job_id} not found for user")
        if not parent_row["complete"]:
            raise ValueError("parent job is not complete yet")
        if parent_row["design_json"] is None:
            raise FileNotFoundError("parent design has not been persisted yet")

        job_id = uuid.uuid4().hex[:12]
        record = JobRecord(
            job_id=job_id,
            user_id=user_id,
            description=instruction,
            parent_job_id=parent_job_id,
            instruction=instruction,
            revision=parent_row["revision"] + 1,
        )
        await execute(
            """
            INSERT INTO jobs (
                job_id, user_id, description, parent_job_id, instruction, revision
            ) VALUES ($1, $2, $3, $4, $5, $6)
            """,
            job_id,
            user_id,
            instruction,
            parent_job_id,
            instruction,
            record.revision,
        )
        self._jobs[job_id] = record
        return record

    async def get_parent_design(
        self, user_id: str, parent_job_id: str
    ) -> dict[str, Any]:
        """Read the parent's persisted CircuitDesign for refinement."""
        row = await fetch_one(
            """
            SELECT design_json FROM jobs
            WHERE job_id = $1 AND user_id = $2 AND complete = TRUE
            """,
            parent_job_id,
            user_id,
        )
        if row is None or row["design_json"] is None:
            raise KeyError(f"parent design for {parent_job_id} unavailable")
        design = row["design_json"]
        if isinstance(design, str):
            design = json.loads(design)
        return design

    # ── streaming events (in-memory) ─────────────────────────────────────

    def get(self, job_id: str) -> JobRecord | None:
        """Return the in-memory record if currently active. Cross-user safe is
        the caller's responsibility; the SSE/event endpoints already check.
        """
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
        # Persist the final event log + artifact index. Design JSON is
        # written separately by the pipeline in persist_design().
        events_json = json.dumps([e.model_dump(mode="json") for e in record.events])
        artifacts_index = json.dumps({k: v.name for k, v in record.artifacts.items()})
        await execute(
            """
            UPDATE jobs
            SET complete        = TRUE,
                events_json     = $2::jsonb,
                artifacts_index = $3::jsonb,
                updated_at      = NOW()
            WHERE job_id = $1
            """,
            job_id,
            events_json,
            artifacts_index,
        )

    def add_artifact(self, job_id: str, name: str, path: Path) -> None:
        record = self._jobs.get(job_id)
        if record is None:
            return
        record.artifacts[name] = path

    async def persist_design(self, job_id: str, design_json: dict[str, Any]) -> None:
        """Save the parsed CircuitDesign so refinement survives redeploys."""
        await execute(
            """
            UPDATE jobs
            SET design_json = $2::jsonb,
                updated_at  = NOW()
            WHERE job_id = $1
            """,
            job_id,
            json.dumps(design_json),
        )

    # ── reads ────────────────────────────────────────────────────────────

    def _hot_artifacts(self, job_id: str) -> dict[str, Path]:
        record = self._jobs.get(job_id)
        return record.artifacts if record else {}

    def _disk_artifacts(self, job_id: str, names: list[str]) -> dict[str, Path]:
        """Reconstruct the artifact index from the persisted filenames."""
        out: dict[str, Path] = {}
        job_dir = GENERATED_ROOT / job_id
        for name in names:
            # Find the file by remembered filename if present; fall back to
            # filenames in the index dict.
            matches = list(job_dir.glob(name)) if "*" in name else [job_dir / name]
            for path in matches:
                if path.exists():
                    out[name] = path
        return out

    async def snapshot_for_user(
        self, user_id: str, job_id: str
    ) -> JobSnapshot | None:
        # Active job: build snapshot from in-memory state. Cheap and avoids
        # races with events being appended.
        live = self._jobs.get(job_id)
        if live is not None and live.user_id == user_id:
            return JobSnapshot(
                job_id=live.job_id,
                complete=live.complete,
                events=live.events,
                artifacts=[
                    ArtifactInfo(name=name, url=f"/api/jobs/{job_id}/artifact/{name}")
                    for name in sorted(live.artifacts)
                ],
                parent_job_id=live.parent_job_id,
                instruction=live.instruction,
                revision=live.revision,
                description=live.description,
                created_at=live.created_at,
            )
        # Otherwise read from Postgres.
        row = await fetch_one(
            """
            SELECT job_id, description, parent_job_id, instruction, revision,
                   complete, created_at, events_json, artifacts_index, design_json
            FROM jobs
            WHERE job_id = $1 AND user_id = $2
            """,
            job_id,
            user_id,
        )
        if row is None:
            return None
        # Resolve artifacts from disk based on the persisted filename map.
        artifacts_idx = row["artifacts_index"] or {}
        if isinstance(artifacts_idx, str):
            artifacts_idx = json.loads(artifacts_idx)
        artifacts: dict[str, Path] = {}
        job_dir = GENERATED_ROOT / job_id
        for name, fname in artifacts_idx.items():
            path = job_dir / fname
            if path.exists():
                artifacts[name] = path
        return _row_to_snapshot(row, artifacts)

    async def artifact_path_for_user(
        self, user_id: str, job_id: str, name: str
    ) -> Path | None:
        # Hot cache first.
        live = self._jobs.get(job_id)
        if live is not None and live.user_id == user_id:
            return live.artifacts.get(name)
        # Disk lookup gated by ownership check.
        row = await fetch_one(
            "SELECT artifacts_index FROM jobs WHERE job_id = $1 AND user_id = $2",
            job_id,
            user_id,
        )
        if row is None:
            return None
        idx = row["artifacts_index"] or {}
        if isinstance(idx, str):
            idx = json.loads(idx)
        fname = idx.get(name)
        if not fname:
            return None
        path = GENERATED_ROOT / job_id / fname
        return path if path.exists() else None

    async def summaries_for_user(self, user_id: str) -> list[JobSummary]:
        rows = await fetch_all(
            """
            SELECT job_id, description, parent_job_id, instruction, revision,
                   complete, created_at, design_json
            FROM jobs
            WHERE user_id = $1
            ORDER BY created_at DESC
            """,
            user_id,
        )
        return [_row_to_summary(r) for r in rows]

    async def lineage_for_user(
        self, user_id: str, job_id: str
    ) -> list[LineageEntry] | None:
        # Walk parent links via a recursive CTE so this is one round-trip.
        rows = await fetch_all(
            """
            WITH RECURSIVE chain AS (
                SELECT job_id, parent_job_id, revision, description,
                       instruction, complete, user_id, 0 AS depth
                FROM jobs
                WHERE job_id = $1 AND user_id = $2

                UNION ALL

                SELECT j.job_id, j.parent_job_id, j.revision, j.description,
                       j.instruction, j.complete, j.user_id, c.depth + 1
                FROM jobs j
                JOIN chain c ON j.job_id = c.parent_job_id
                WHERE j.user_id = $2
            )
            SELECT * FROM chain ORDER BY depth DESC
            """,
            job_id,
            user_id,
        )
        if not rows:
            return None
        return [
            LineageEntry(
                job_id=r["job_id"],
                revision=r["revision"],
                title=(r["instruction"] if r["revision"] and r["instruction"] else r["description"]) or r["job_id"],
                complete=r["complete"],
            )
            for r in rows
        ]

    async def delete_for_user(self, user_id: str, job_id: str) -> list[str]:
        """Delete a job and all its descendant revisions.

        Returns the list of job_ids that were actually deleted (parent +
        every revision rooted at it). Raises ``KeyError`` when the job
        doesn't exist for this user.

        We cascade because keeping orphaned revisions around is confusing
        — if you delete the original prompt, the refinement chain on top
        of it has no anchor in the UI.
        """
        # Verify ownership before doing anything destructive.
        owns_root = await fetch_one(
            "SELECT 1 FROM jobs WHERE job_id = $1 AND user_id = $2",
            job_id,
            user_id,
        )
        if owns_root is None:
            raise KeyError(f"job {job_id} not found for user")

        # Gather every descendant id (BFS through parent_job_id pointers).
        # The DB has ``ON DELETE SET NULL`` on parent_job_id, so a single
        # DELETE on the root would orphan its children rather than remove
        # them — we want full cascade, hence collecting + deleting all.
        all_ids: list[str] = [job_id]
        frontier: list[str] = [job_id]
        while frontier:
            child_rows = await fetch_all(
                """
                SELECT job_id FROM jobs
                WHERE user_id = $1 AND parent_job_id = ANY($2::text[])
                """,
                user_id,
                frontier,
            )
            frontier = [r["job_id"] for r in child_rows]
            all_ids.extend(frontier)

        # Drop in-memory cache entries first so any lingering streams
        # don't try to write to a record that no longer exists.
        for jid in all_ids:
            self._jobs.pop(jid, None)

        # Delete SQL rows. Children must go before parents because of the
        # FK; reversing the BFS order achieves that (deepest revisions
        # first, root last).
        for jid in reversed(all_ids):
            await execute(
                "DELETE FROM jobs WHERE job_id = $1 AND user_id = $2",
                jid,
                user_id,
            )

        # Remove on-disk artifacts. Best-effort — we still want the SQL
        # delete to succeed even if a file is locked.
        import shutil

        for jid in all_ids:
            output_dir = GENERATED_ROOT / jid
            if output_dir.exists():
                try:
                    shutil.rmtree(output_dir)
                except Exception:  # noqa: BLE001
                    pass

        return all_ids

    async def owns(self, user_id: str, job_id: str) -> bool:
        """Used by SSE before opening the stream."""
        live = self._jobs.get(job_id)
        if live is not None:
            return live.user_id == user_id
        row = await fetch_one(
            "SELECT 1 FROM jobs WHERE job_id = $1 AND user_id = $2",
            job_id,
            user_id,
        )
        return row is not None


STORE = JobStore()
