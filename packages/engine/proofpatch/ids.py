"""Identifier generation for ProofPatch runs.

We use a ULID-like, lexicographically sortable identifier instead of a UUID so
that run IDs sort by creation time. The format mirrors the plan's examples
(``pp_01J...``) without pulling in an external ULID dependency.
"""

from __future__ import annotations

import os
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode(value: int, length: int) -> str:
    chars = ["0"] * length
    for i in range(length - 1, -1, -1):
        chars[i] = _CROCKFORD[value & 0x1F]
        value >>= 5
    return "".join(chars)


def new_run_id(prefix: str = "pp") -> str:
    """Return a new run id such as ``pp_01J8ZK4Q9T3F2M7B7X0C5N6PQR``."""

    timestamp_ms = int(time.time() * 1000)
    time_part = _encode(timestamp_ms, 10)
    random_part = _encode(int.from_bytes(os.urandom(10), "big"), 16)
    return f"{prefix}_{time_part}{random_part}"


__all__ = ["new_run_id"]
