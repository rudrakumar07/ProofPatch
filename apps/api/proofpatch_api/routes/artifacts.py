"""Artifact endpoint with strict path containment (no arbitrary filesystem reads)."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from ..services import run_service

router = APIRouter(prefix="/api", tags=["artifacts"])


@router.get("/runs/{run_id}/artifact/{path:path}")
def get_artifact(run_id: str, path: str):
    if run_service.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown run: {run_id}")

    store = run_service.run_artifact_store(run_id)
    resolved = store.safe_artifact_path(path)
    if resolved is None or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")

    text = resolved.read_text(encoding="utf-8", errors="replace")
    if resolved.suffix == ".json":
        try:
            return {"path": path, "json": json.loads(text)}
        except json.JSONDecodeError:
            pass
    return {"path": path, "text": text}


__all__ = ["router"]
