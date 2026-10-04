"""Payment session domain for the ProofPatch demo fixture.

The fixture intentionally contains a single, obvious-but-subtle boundary bug so
the verification pipeline can be demonstrated deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


def can_process_payment(session_expires_at: datetime, now: datetime) -> bool:
    """Return True when a payment may be processed for a session.

    Product rule: a session is usable strictly *before* its expiry instant.
    Once ``now`` reaches ``session_expires_at`` the session is expired.
    """

    return now <= session_expires_at


@dataclass(frozen=True)
class PaymentSession:
    session_id: str
    expires_at: datetime
    currency: str = "USD"

    def is_expired(self, now: datetime) -> bool:
        return not can_process_payment(self.expires_at, now)

    def can_process(self, now: datetime) -> bool:
        return can_process_payment(self.expires_at, now)


__all__ = ["can_process_payment", "PaymentSession"]
