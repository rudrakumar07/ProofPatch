# ProofPatch demo fixture — payment session bug

A tiny, dependency-free Python project (pytest only) used to demonstrate the
ProofPatch verification loop deterministically.

## The bug

`can_process_payment` treats the exact expiry instant as *valid* (`now <=
expires_at`) when the product rule requires it to be *expired* (`now <
expires_at`). Everything else in the module is correct.

## Layout

```
src/payment/session.py   # contains the one-line boundary bug
tests/test_session.py    # 5 passing tests + 1 known failing reproduction test
bug.md                   # the bug report handed to ProofPatch
```

## Reproduce

```bash
pytest -q tests/test_session.py::test_payment_rejected_at_exact_expiry
```

This fails on the baseline. The correct patch flips `<=` to `<`, after which all
tests (existing + generated) pass.
