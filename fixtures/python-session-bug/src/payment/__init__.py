"""Payment domain package for the ProofPatch demo fixture."""

from .session import PaymentSession, can_process_payment

__all__ = ["PaymentSession", "can_process_payment"]
