"""ProofPatch engine.

The engine is deliberately independent of FastAPI and React. It exposes a small,
deterministic verification pipeline that the CLI and the API both call.

Core principle: LLM output is a proposal; verification state is produced by
deterministic code.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
