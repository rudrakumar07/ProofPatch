# Payment allowed at exact session expiry

A payment session should no longer be usable once its expiry timestamp is reached.
Currently a payment attempted exactly at `expires_at` is accepted.

Expected: `now >= expires_at` should be treated as expired.
Actual: equality is treated as valid.

Reproduction:

```bash
pytest -q tests/test_session.py::test_payment_rejected_at_exact_expiry
```
