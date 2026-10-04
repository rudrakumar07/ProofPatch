"""API response/response schemas.

``POST /api/runs`` reuses the engine's ``RunRequest`` so the CLI and the API
accept exactly the same payload.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from proofpatch.domain import RunRequest
from pydantic import BaseModel, Field

__all__ = ["EventOut", "RunCreated", "RunOut", "RunRequest"]


class RunCreated(BaseModel):
    run_id: str
    status: str


class RunOut(BaseModel):
    run_id: str
    status: str
    verdict: str | None = None
    score: int | None = None
    issue_title: str = ""
    repo_path: str = ""
    base_commit: str | None = None
    repro_command: str | None = None
    current_step: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    artifact_dir: str = ""


class EventOut(BaseModel):
    sequence: int
    timestamp: datetime
    type: str
    step: str | None = None
    status: str | None = None
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class HealthOut(BaseModel):
    ok: bool = True
    provider_mode: str = "fake"
    version: str = "0.1.0"
