"""Cline SDK provider.

This is the *only* LLM integration in ProofPatch v0.1. The Cline SDK is a
TypeScript package, so we drive it through a tiny Node bridge
(``packages/cline-bridge``) that runs one single-shot agent turn and prints JSON.

Trust boundary: the bridge always runs the agent with ``tools: []``. The agent
can therefore only *return text* -- it cannot read, edit, or execute anything in
the repository under verification. Every command ProofPatch runs is chosen by
deterministic code, never by the model.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from .provider import CallRecorder, LLMCallRecord, LLMError, _hash, extract_json

DEFAULT_PROVIDER_ID = "cline"
DEFAULT_BRIDGE_RELATIVE = Path("packages") / "cline-bridge"
BRIDGE_ENTRY = Path("src") / "bridge.mjs"

JSON_ONLY_SUFFIX = (
    "\n\nIMPORTANT: Reply with a single valid JSON object and nothing else. "
    "Do not wrap it in markdown code fences and do not add prose before or after it."
)


def cline_settings_path() -> Path:
    """Location of the Cline CLI/IDE provider settings."""

    return Path.home() / ".cline" / "data" / "settings" / "providers.json"


def discover_cline_auth(provider_id: str = DEFAULT_PROVIDER_ID) -> tuple[str | None, str | None]:
    """Read the access token and default model from the local Cline settings.

    Returns ``(access_token, model_id)``; either may be ``None`` when the machine
    has no matching Cline configuration. Other credentials are never returned.
    """

    path = cline_settings_path()
    if not path.exists():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None

    entry = (data.get("providers") or {}).get(provider_id) or {}
    settings = entry.get("settings") or {}
    token = (settings.get("auth") or {}).get("accessToken")
    model = settings.get("model")
    return (token or None), (model or None)


def resolve_bridge_dir(explicit: str | os.PathLike[str] | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    # <repo>/packages/engine/proofpatch/llm/cline_sdk.py -> <repo>
    repo_root = Path(__file__).resolve().parents[4]
    return (repo_root / DEFAULT_BRIDGE_RELATIVE).resolve()


def resolve_node_bin(explicit: str | None = None) -> str | None:
    candidate = explicit or os.environ.get("PROOFPATCH_CLINE_NODE_BIN") or "node"
    return shutil.which(candidate)


class ClineSDKProvider:
    """Structured-output provider backed by the Cline SDK agent runtime."""

    name = "cline-sdk"

    def __init__(
        self,
        *,
        provider_id: str = DEFAULT_PROVIDER_ID,
        model_id: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        node_bin: str | None = None,
        bridge_dir: str | os.PathLike[str] | None = None,
        timeout_seconds: int = 180,
        max_iterations: int = 1,
        max_retries: int = 1,
        recorder: CallRecorder | None = None,
        autodiscover: bool = True,
    ) -> None:
        self.provider_id = provider_id
        discovered_token: str | None = None
        discovered_model: str | None = None
        if autodiscover:
            discovered_token, discovered_model = discover_cline_auth(provider_id)

        self.api_key = api_key or os.environ.get("PROOFPATCH_CLINE_API_KEY") or discovered_token
        self.model_id = (
            model_id or os.environ.get("PROOFPATCH_CLINE_MODEL_ID") or discovered_model or ""
        )
        if not self.model_id:
            raise LLMError(
                "No Cline model configured. Set PROOFPATCH_CLINE_MODEL_ID or sign in with Cline "
                "so ~/.cline/data/settings/providers.json contains a model."
            )

        self.base_url = base_url or os.environ.get("PROOFPATCH_CLINE_BASE_URL") or ""
        self.node_bin = node_bin
        self.bridge_dir = resolve_bridge_dir(bridge_dir)
        self.timeout_seconds = timeout_seconds
        self.max_iterations = max_iterations
        self.max_retries = max_retries
        self.recorder = recorder

    # -- metadata ----------------------------------------------------------- #
    @property
    def model(self) -> str:
        return self.model_id

    def bridge_entry(self) -> Path:
        return self.bridge_dir / BRIDGE_ENTRY

    def preflight(self) -> list[str]:
        """Return a list of configuration problems (empty means ready)."""

        problems: list[str] = []
        if resolve_node_bin(self.node_bin) is None:
            problems.append(
                "Node.js 22+ is required for Cline SDK mode but 'node' was not found on PATH."
            )
        if not self.bridge_entry().exists():
            problems.append(
                f"Cline SDK bridge not found at {self.bridge_entry()}. "
                "Run 'npm install' in packages/cline-bridge."
            )
        elif not (self.bridge_dir / "node_modules" / "@cline" / "sdk").exists():
            problems.append(
                f"@cline/sdk is not installed in {self.bridge_dir}. "
                "Run 'npm install' in packages/cline-bridge."
            )
        if not self.api_key:
            problems.append(
                "No Cline credentials found. Sign in with the Cline CLI/IDE, "
                "or set PROOFPATCH_CLINE_API_KEY."
            )
        return problems

    # -- core call ---------------------------------------------------------- #
    def _run_bridge(self, request: dict[str, Any]) -> dict[str, Any]:
        node = resolve_node_bin(self.node_bin)
        if node is None:
            raise LLMError("Node.js is required for Cline SDK mode but was not found on PATH.")
        entry = self.bridge_entry()
        if not entry.exists():
            raise LLMError(f"Cline SDK bridge not found at {entry}.")

        env = dict(os.environ)
        env.setdefault("CLINE_NO_INTERACTIVE", "1")
        # Keep node diagnostics out of stderr; stdout must stay parseable JSON.
        env.setdefault("NODE_NO_WARNINGS", "1")
        env.setdefault("AI_SDK_LOG_WARNINGS", "0")

        try:
            proc = subprocess.run(  # noqa: S603 -- fixed local argv, not shell text
                [node, str(entry)],
                input=json.dumps(request),
                capture_output=True,
                text=True,
                errors="replace",
                timeout=self.timeout_seconds,
                cwd=str(self.bridge_dir),
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMError(
                f"Cline SDK agent timed out after {self.timeout_seconds}s."
            ) from exc

        payload: dict[str, Any] | None = None
        stdout = (proc.stdout or "").strip()
        if stdout:
            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError:
                payload = None

        if payload is None:
            detail = (proc.stderr or stdout or "").strip()[-1000:]
            raise LLMError(
                f"Cline SDK bridge produced no parseable JSON (exit {proc.returncode}): {detail}"
            )
        if not payload.get("ok"):
            raise LLMError(f"Cline SDK agent failed: {payload.get('error')}")
        return payload

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
        temperature: float = 0.0,  # interface parity; sampling is controlled by the SDK
        agent: str = "",
    ) -> BaseModel:
        prompt = user_prompt
        last_error = ""
        for attempt in range(1, self.max_retries + 2):
            request: dict[str, Any] = {
                "systemPrompt": system_prompt + JSON_ONLY_SUFFIX,
                "userPrompt": prompt,
                "providerId": self.provider_id,
                "modelId": self.model_id,
                "maxIterations": self.max_iterations,
                "cwd": str(Path.cwd()),
            }
            if self.api_key:
                request["apiKey"] = self.api_key
            if self.base_url:
                request["baseUrl"] = self.base_url

            started = time.perf_counter()
            payload = await asyncio.to_thread(self._run_bridge, request)
            latency_ms = int((time.perf_counter() - started) * 1000)
            text = payload.get("text") or ""
            usage = payload.get("usage") or {}

            try:
                parsed = response_model.model_validate_json(extract_json(text))
            except (ValidationError, ValueError) as exc:
                last_error = str(exc)
                self._record(
                    agent, system_prompt + prompt, text, latency_ms, usage, "invalid", attempt
                )
                prompt = (
                    user_prompt
                    + "\n\nYour previous response was not valid JSON for the required schema. "
                    + f"Validation error:\n{last_error}\nReturn ONLY the corrected JSON object."
                )
                continue

            self._record(agent, system_prompt + prompt, text, latency_ms, usage, "ok", attempt)
            return parsed

        raise LLMError(f"Cline SDK agent returned invalid structured output: {last_error}")

    def _record(
        self,
        agent: str,
        prompt_text: str,
        content: str,
        latency_ms: int,
        usage: dict[str, Any],
        validation: str,
        attempt: int,
    ) -> None:
        if self.recorder is None:
            return
        self.recorder(
            LLMCallRecord(
                agent=agent,
                model=self.model_id,
                prompt_hash=_hash(prompt_text),
                response_hash=_hash(content),
                latency_ms=latency_ms,
                prompt_tokens=usage.get("inputTokens"),
                completion_tokens=usage.get("outputTokens"),
                validation=validation,
                attempt=attempt,
            )
        )


__all__ = [
    "ClineSDKProvider",
    "discover_cline_auth",
    "resolve_bridge_dir",
    "resolve_node_bin",
    "cline_settings_path",
    "DEFAULT_PROVIDER_ID",
    "JSON_ONLY_SUFFIX",
]

