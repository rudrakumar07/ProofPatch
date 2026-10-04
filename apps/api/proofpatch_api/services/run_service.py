"""Run service: create runs, execute them in a bounded pool, persist events.

The orchestrator runs in a small thread pool (max 2 by default). Each worker has
its own event loop, so blocking repository/command work never stalls the API's
event loop or the SSE stream.
"""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from proofpatch.artifacts import ArtifactStore
from proofpatch.config import Settings
from proofpatch.domain import RunEventModel, RunRequest, utcnow
from proofpatch.ids import new_run_id
from proofpatch.orchestrator import Orchestrator

from ..db import session_scope
from ..models import Run, RunEvent

MAX_CONCURRENT_RUNS = 2

_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_RUNS, thread_name_prefix="proofpatch-run")


def _naive(dt: datetime) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _update_run(run_id: str, **fields: Any) -> None:
    with session_scope() as session:
        row = session.get(Run, run_id)
        if row is None:
            return
        for key, value in fields.items():
            setattr(row, key, value)
        row.updated_at = _naive(utcnow())
        session.flush()


def _make_listener(run_id: str):
    def listener(event: RunEventModel) -> None:
        try:
            with session_scope() as session:
                session.add(
                    RunEvent(
                        run_id=run_id,
                        sequence=event.sequence,
                        created_at=_naive(event.timestamp),
                        event_type=event.type,
                        step=event.step,
                        status=event.status,
                        message=event.message,
                        payload_json=json.dumps(event.payload or {}),
                    )
                )
                if event.type == "run_status_changed" and event.status:
                    row = session.get(Run, run_id)
                    if row is not None:
                        row.status = event.status
                        row.updated_at = _naive(utcnow())
                elif event.type == "step_completed" and event.step == "repository_prepared":
                    row = session.get(Run, run_id)
                    commit = (event.payload or {}).get("base_commit")
                    if row is not None and commit:
                        row.base_commit = commit
                        row.updated_at = _naive(utcnow())
                elif event.type == "run_error":
                    row = session.get(Run, run_id)
                    if row is not None:
                        row.error_message = event.message
        except Exception:
            # Event persistence must never break the verification run.
            pass

    return listener

def _execute(run_id: str, request: RunRequest) -> None:
    settings = Settings()
    orchestrator = Orchestrator(settings=settings, listener=_make_listener(run_id))
    try:
        result = asyncio.run(orchestrator.execute_run(request, run_id=run_id))
    except Exception as exc:  # noqa: BLE001 - last-resort boundary
        _update_run(run_id, status="ERROR", error_message=f"{type(exc).__name__}: {exc}")
        return
    _update_run(
        run_id,
        status=result.status.value,
        verdict=result.verdict.value,
        score=result.score,
        error_message=result.error,
        completed_at=_naive(utcnow()),
    )


def create_run(request: RunRequest) -> str:
    """Insert a run row and queue it for execution. Returns the run id."""

    run_id = new_run_id()
    now = _naive(utcnow())
    with session_scope() as session:
        session.add(
            Run(
                id=run_id,
                status="CREATED",
                repo_path=str(request.repository.path),
                issue_title=request.issue.title,
                issue_description=request.issue.description,
                repro_command=request.issue.repro_command,
                artifact_dir=str(Settings().run_artifact_dir(run_id)),
                created_at=now,
                updated_at=now,
            )
        )
    _executor.submit(_execute, run_id, request)
    return run_id


def get_run(run_id: str) -> Run | None:
    with session_scope() as session:
        return session.get(Run, run_id)


def list_runs(limit: int = 50) -> list[Run]:
    from sqlalchemy import select

    with session_scope() as session:
        rows = session.execute(
            select(Run).order_by(Run.created_at.desc()).limit(limit)
        ).scalars().all()
        return list(rows)


def get_events(run_id: str, after_sequence: int = 0) -> list[RunEvent]:
    from sqlalchemy import select

    with session_scope() as session:
        rows = session.execute(
            select(RunEvent)
            .where(RunEvent.run_id == run_id, RunEvent.sequence > after_sequence)
            .order_by(RunEvent.sequence.asc())
        ).scalars().all()
        return list(rows)


def latest_step(run_id: str) -> str | None:
    events = get_events(run_id)
    steps = [e.step for e in events if e.step and e.event_type == "step_completed"]
    return steps[-1] if steps else None


def run_artifact_store(run_id: str) -> ArtifactStore:
    return ArtifactStore.for_existing(Settings().data_dir, run_id)


def run_exists(run_id: str) -> bool:
    return get_run(run_id) is not None
