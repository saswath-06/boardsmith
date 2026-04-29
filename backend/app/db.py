"""Async Postgres connection pool + schema migration for Boardsmith.

We talk to Supabase Postgres directly via ``asyncpg`` rather than going
through PostgREST. Auth is enforced application-side: every job query
filters by ``user_id`` extracted from the verified Supabase JWT.

Schema is created idempotently on first connection — no separate
migration step is needed.
"""
from __future__ import annotations

import os
from typing import Any

import asyncpg

_pool: asyncpg.Pool | None = None


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id          TEXT        PRIMARY KEY,
    user_id         UUID        NOT NULL,
    description     TEXT        NOT NULL DEFAULT '',
    parent_job_id   TEXT        REFERENCES jobs(job_id) ON DELETE SET NULL,
    instruction     TEXT,
    revision        INTEGER     NOT NULL DEFAULT 0,
    complete        BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Persisted snapshot blobs. design_json is the parsed CircuitDesign so
    -- refinements can reload after a Railway redeploy. events_json is the
    -- replay log so loadJob() rebuilds viewer state without re-running.
    design_json     JSONB,
    events_json     JSONB       NOT NULL DEFAULT '[]'::jsonb,
    artifacts_index JSONB       NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS jobs_user_idx
    ON jobs(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS jobs_parent_idx
    ON jobs(parent_job_id);
"""


async def init_pool() -> asyncpg.Pool:
    """Create the connection pool and run schema migration. Idempotent."""
    global _pool
    if _pool is not None:
        return _pool

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError(
            "DATABASE_URL is not set. Add it to backend/.env "
            "(see backend/.env.example)."
        )

    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=1,
        max_size=10,
        command_timeout=30,
        # Statement cache must be off for transaction-mode pgbouncer/pooler.
        # Harmless for direct connections.
        statement_cache_size=0,
    )

    async with _pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)

    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool is not initialized — call init_pool() first")
    return _pool


async def fetch_one(query: str, *args: Any) -> asyncpg.Record | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)


async def fetch_all(query: str, *args: Any) -> list[asyncpg.Record]:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def execute(query: str, *args: Any) -> str:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)
