"""Central configuration for the ProofPatch engine.

All settings come from environment variables (optionally loaded from a local
``.env`` file). The engine's LLM integration is the Cline SDK; Cline account
credentials and the default model are auto-discovered from the local
``~/.cline`` settings when not set explicitly.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _alias(*names: str) -> AliasChoices:
    return AliasChoices(*names)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- ProofPatch runtime ----
    data_dir: Path = Field(
        default=Path(".proofpatch"),
        validation_alias=_alias("PROOFPATCH_DATA_DIR", "data_dir"),
    )
    database_url: str = Field(
        default="sqlite:///./.proofpatch/proofpatch.db",
        validation_alias=_alias("PROOFPATCH_DATABASE_URL", "database_url"),
    )
    keep_worktrees: bool = Field(
        default=False,
        validation_alias=_alias("PROOFPATCH_KEEP_WORKTREES", "keep_worktrees"),
    )
    default_timeout: int = Field(
        default=120,
        validation_alias=_alias("PROOFPATCH_DEFAULT_TIMEOUT", "default_timeout"),
    )
    max_patch_files: int = Field(
        default=8,
        validation_alias=_alias("PROOFPATCH_MAX_PATCH_FILES", "max_patch_files"),
    )
    max_patch_lines: int = Field(
        default=400,
        validation_alias=_alias("PROOFPATCH_MAX_PATCH_LINES", "max_patch_lines"),
    )
    cline_provider_id: str = Field(
        default="cline",
        validation_alias=_alias("PROOFPATCH_CLINE_PROVIDER_ID", "cline_provider_id"),
    )
    cline_model_id: str = Field(
        default="",
        validation_alias=_alias("PROOFPATCH_CLINE_MODEL_ID", "cline_model_id"),
    )
    cline_api_key: str = Field(
        default="",
        validation_alias=_alias("PROOFPATCH_CLINE_API_KEY", "cline_api_key"),
    )
    cline_base_url: str = Field(
        default="",
        validation_alias=_alias("PROOFPATCH_CLINE_BASE_URL", "cline_base_url"),
    )
    cline_node_bin: str = Field(
        default="",
        validation_alias=_alias("PROOFPATCH_CLINE_NODE_BIN", "cline_node_bin"),
    )
    cline_bridge_dir: str = Field(
        default="",
        validation_alias=_alias("PROOFPATCH_CLINE_BRIDGE_DIR", "cline_bridge_dir"),
    )
    cline_timeout_seconds: int = Field(
        default=180,
        validation_alias=_alias("PROOFPATCH_CLINE_TIMEOUT_SECONDS", "cline_timeout_seconds"),
    )
    cline_max_iterations: int = Field(
        default=1,
        validation_alias=_alias("PROOFPATCH_CLINE_MAX_ITERATIONS", "cline_max_iterations"),
    )
    cline_max_retries: int = Field(
        default=1,
        validation_alias=_alias("PROOFPATCH_CLINE_MAX_RETRIES", "cline_max_retries"),
    )

    @model_validator(mode="after")
    def _resolve_paths(self) -> Settings:
        # data_dir MUST be absolute: Git worktree paths are passed to `git -C`
        # and a relative path would otherwise be resolved against the target
        # repository rather than the ProofPatch process working directory.
        self.data_dir = Path(self.data_dir).expanduser().resolve()
        return self

    def run_artifact_dir(self, run_id: str) -> Path:
        return Path(self.data_dir) / "runs" / run_id

    def validate_for_run(self) -> list[str]:
        """Return a list of configuration problems (empty means OK).

        The Cline account may sign in via the local ``~/.cline`` settings, so
        this check succeeds when auto-discovery finds credentials; otherwise it
        fails with an actionable message.
        """

        from .llm.cline_sdk import resolve_bridge_dir, resolve_node_bin

        problems: list[str] = []
        if resolve_node_bin(self.cline_node_bin or None) is None:
            problems.append(
                "Node.js 22+ is required for Cline SDK mode but 'node' was not found on PATH."
            )
        bridge = resolve_bridge_dir(self.cline_bridge_dir or None) / "src" / "bridge.mjs"
        if not bridge.exists():
            problems.append(f"Cline SDK bridge not found at {bridge}.")
        elif not (bridge.parent.parent / "node_modules" / "@cline" / "sdk").exists():
            problems.append(f"@cline/sdk is not installed. Run 'npm install' in {bridge.parent.parent}.")
        return problems


def get_settings(**overrides) -> Settings:
    """Build a settings object, applying explicit overrides on top of env vars."""

    settings = Settings()
    if overrides:
        settings = settings.model_copy(update=overrides)
    return settings


__all__ = ["Settings", "get_settings"]
