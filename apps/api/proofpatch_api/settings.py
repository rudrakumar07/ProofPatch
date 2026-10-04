"""API settings: reuse the engine settings and add API-specific options."""

from __future__ import annotations

from proofpatch.config import Settings as EngineSettings

__all__ = ["EngineSettings", "get_settings"]


def get_settings(**overrides) -> EngineSettings:
    return EngineSettings(**overrides)
