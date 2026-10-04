"""API tests conftest.

The engine's test double (``StubLLMProvider``) lives with the engine's test
suite. Adding that directory to ``sys.path`` lets the API tests reuse it so the
API integration tests stay deterministic and offline -- no live model calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

ENGINE_TESTS = Path(__file__).resolve().parents[3] / "packages" / "engine" / "tests"
if ENGINE_TESTS.exists() and str(ENGINE_TESTS) not in sys.path:
    sys.path.insert(0, str(ENGINE_TESTS))
