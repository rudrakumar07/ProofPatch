from datetime import datetime, timedelta, timezone

from payment.session import PaymentSession, can_process_payment

EXPIRES = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_payment_allowed_before_expiry():
    assert can_process_payment(EXPIRES, EXPIRES - timedelta(seconds=1)) is True


def test_payment_denied_after_expiry():
    assert can_process_payment(EXPIRES, EXPIRES + timedelta(seconds=1)) is False


def test_session_id_is_preserved():
    session = PaymentSession(session_id="sess_123", expires_at=EXPIRES)
    assert session.session_id == "sess_123"


def test_currency_defaults_to_usd():
    session = PaymentSession(session_id="sess_123", expires_at=EXPIRES)
    assert session.currency == "USD"


def test_is_expired_after_expiry():
    session = PaymentSession(session_id="sess_123", expires_at=EXPIRES)
    assert session.is_expired(EXPIRES + timedelta(seconds=1)) is True


def test_payment_rejected_at_exact_expiry():
    """Known failing reproduction test: at the expiry instant the session is expired."""

    assert can_process_payment(EXPIRES, EXPIRES) is False
