"""Run endpoints: create, inspect, stream events, and fetch reports."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from proofpatch.domain import RunRequest

from ..schemas import EventOut, RunCreated, RunOut
from ..services import run_service

router = APIRouter(prefix="/api", tags=["runs"])

TERMINAL_STATUSES = {"VERIFIED", "NEEDS_REVIEW", "REJECTED", "ERROR"}


def _run_out(row) -> RunOut:
    return RunOut(
        run_id=row.id,
        status=row.status,
        verdict=row.verdict,
        score=row.score,
        issue_title=row.issue_title,
        repo_path=row.repo_path,
        base_commit=row.base_commit,
        repro_command=row.repro_command,
        current_step=run_service.latest_step(row.id),
        created_at=row.created_at,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
        error_message=row.error_message,
        artifact_dir=row.artifact_dir,
    )


def _require_run(run_id: str):
    row = run_service.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown run: {run_id}")
    return row


@router.post("/runs", response_model=RunCreated, status_code=202)
def create_run(request: RunRequest) -> RunCreated:
    run_id = run_service.create_run(request)
    return RunCreated(run_id=run_id, status="CREATED")


@router.get("/runs")
def list_runs() -> list[RunOut]:
    return [_run_out(row) for row in run_service.list_runs()]


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str) -> RunOut:
    return _run_out(_require_run(run_id))


@router.get("/runs/{run_id}/events.json")
def list_events_json(run_id: str, after: int = 0) -> list[EventOut]:
    """Non-streaming events endpoint used by the polling fallback."""

    _require_run(run_id)
    return [
        EventOut(
            sequence=event.sequence,
            timestamp=event.created_at,
            type=event.event_type,
            step=event.step,
            status=event.status,
            message=event.message,
            payload=json.loads(event.payload_json or "{}"),
        )
        for event in run_service.get_events(run_id, after)
    ]


@router.get("/runs/{run_id}/events")
async def stream_events(run_id: str):
    _require_run(run_id)

    async def event_source() -> Iterator[str]:
        last_sequence = 0
        while True:
            events = run_service.get_events(run_id, last_sequence)
            for event in events:
                last_sequence = max(last_sequence, event.sequence)
                payload = EventOut(
                    sequence=event.sequence,
                    timestamp=event.created_at,
                    type=event.event_type,
                    step=event.step,
                    status=event.status,
                    message=event.message,
                    payload=json.loads(event.payload_json or "{}"),
                )
                yield f"event: {event.event_type}\ndata: {payload.model_dump_json()}\n\n"

            row = run_service.get_run(run_id)
            if row is None:
                break
            if row.status in TERMINAL_STATUSES and not events:
                yield (
                    "event: done\n"
                    f"data: {json.dumps({'status': row.status, 'verdict': row.verdict, 'score': row.score})}\n\n"
                )
                break
            await asyncio.sleep(0.4)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/runs/{run_id}/report")
def get_report(run_id: str) -> JSONResponse:
    _require_run(run_id)
    store = run_service.run_artifact_store(run_id)
    if not store.exists("report.json"):
        raise HTTPException(status_code=409, detail="Report not available yet.")
    return JSONResponse(content=store.read_json("report.json"))


@router.get("/runs/{run_id}/report.md")
def get_report_markdown(run_id: str):
    _require_run(run_id)
    store = run_service.run_artifact_store(run_id)
    if not store.exists("report.md"):
        raise HTTPException(status_code=409, detail="Report not available yet.")
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(
        store.read_text("report.md"),
        media_type="text/markdown; charset=utf-8",
    )


@router.get("/runs/{run_id}/diff")
def get_diff(run_id: str):
    _require_run(run_id)
    store = run_service.run_artifact_store(run_id)
    if not store.exists("candidate.diff"):
        raise HTTPException(status_code=409, detail="Diff not available yet.")
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(store.read_text("candidate.diff"), media_type="text/plain; charset=utf-8")


__all__ = ["router"]
