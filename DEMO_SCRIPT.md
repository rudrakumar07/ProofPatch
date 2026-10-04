
# ProofPatch × Cline — hackathon demo script (3–5 minutes)

**Story:** *Cline wrote the fix. ProofPatch proved it.*

> Read the bold lead-ins as your narration. Everything in `code` blocks is a command to run.
> Before recording: `make setup`, `cd packages/cline-bridge && npm install`,
> copy `.env.example` → `.env` with a funded `PROOFPATCH_CLINE_API_KEY`.

---

## 0. The problem (15s)

**"AI code tools will happily hand you a patch. But how do you know it's safe?**
**ProofPatch doesn't ask you to trust the model — it collects evidence."**

---

## 1. Show the bug (30s)

```bash
cd fixtures/python-session-bug
pytest -q tests/test_session.py::test_payment_rejected_at_exact_expiry
```

**"Line one: a payment made at the exact session expiry should be rejected. It passes instead.**
**That's the bug — a `<=` that should be a `<`."**

---

## 2. Start ProofPatch (30s)

```bash
cd ../..   # back at the repo root
make demo            # or: proofpatch verify --repo fixtures/python-session-bug \
                     #        --issue fixtures/python-session-bug/bug.md \
                     #        --repro "pytest -q tests/test_session.py::test_payment_rejected_at_exact_expiry"
```

```text
  → status: PREPARING
  ✓ Repository prepared (isolated baseline/candidate worktrees)
  → status: BASELINE_RUNNING
  ✓ Baseline reproduction command executed
```

**"ProofPatch freezes the repo at its current commit, builds two isolated worktrees —**
**baseline and candidate — and reproduces the bug on the baseline first.**
**It never touches your branch."**

---

## 3. Analysis, by the Cline SDK (30s)

```text
  → status: ANALYZING
  ✓ Root cause analyzed
```

**"Then it asks the Cline SDK — the same agent runtime that powers Cline —**
**for a root-cause hypothesis. Watch the dashboard."**

Open `http://127.0.0.1:8000/` → the run → **Timeline** tab.

**"Same run, live: status, timeline, evidence — no refresh needed."**

---

## 4. The patch (30s)

```text
  → status: PATCH_GENERATING
  ✓ Candidate patch generated
```

**"The SDK proposes a patch. Before anything runs, ProofPatch validates it:**
**no test edits, no path tricks, no oversized diffs — and it must `git apply` cleanly."**

Show the **Patch** tab → the diff:

```diff
-    return now <= session_expires_at
+    return now < session_expires_at
```

---

## 5. The money moment (45s)

```text
  ✓ Verification tests generated and locked
  ✗ Baseline verification tests executed
  ✓ Candidate patch applied to isolated worktree
  ✓ Candidate verification tests executed
```

**"Here is the key idea: ProofPatch writes its *own* tests — without ever showing the**
**agent the patch — then locks them by SHA-256 and runs the *identical bytes* before and after."**

Show the **Generated tests** tab:

```text
Generated regression tests:
  Baseline:  FAIL
  Candidate: PASS
```

**"A test that fails before the patch and passes after it — that's causal evidence,**
**not a claim."**

---

## 6. Regressions and static checks (20s)

```text
  ✓ Candidate existing test suite executed
  ✓ Candidate static/syntax checks executed
```

**"Then the full suite, baseline versus candidate: zero new failures.**
**Static checks: no new findings."**

Show the **Evidence** tab → the checklist table.

---

## 7. The Proof Report and verdict (30s)

```text
Evidence score: 100 / 100
Verdict: VERIFIED — Ready for human review
```

**"An evidence score — not a probability, not a guarantee — plus every reason behind it,**
**in a report you can read without the UI."**

Show the **Report** tab → scroll the Markdown.

**End on the line:**
**"Don't trust an AI patch because the AI says it works. Verify it with reproducible**
**evidence. That's ProofPatch — Cline SDK powered."**

---

## Appendix A — Real-repo run (optional 60s segment)

> Everything below runs on repos prepared under `targets/` (gitignored — they are working
> material, never committed).

**"The same pipeline, unchanged, verified a real bug in the `rich` library —**
**issue #3299, `Segment._split_cells`: VERIFIED 100/100, a minimal 1-line patch,**
**generated differential tests, zero new regressions across its 800-test suite —**
**and the famous `rich` repository was never modified."**

Show the run's `report.md` evidence table; show `git status` clean and `git worktree list`
in `targets/rich`.

**Why only Python targets here:** ProofPatch v0.1 verifies **Python** projects only. The Cline
repository itself is TypeScript (`sdk/packages/*`), so it cannot be the patient yet — that's what
Stretch 4 (JS/TS adapter) is for. But Cline already stars in this demo the other way: **every
model call in this pipeline runs through the Cline SDK agent runtime** (`packages/cline-bridge`,
`providerId=openai-compatible`, `tools: []` so the agent can only return text). The Cline repo is
checked out at `targets/cline-repo` so you can hold up its SDK package while saying this:

```bash
ls targets/cline-repo/sdk/packages   # agents core llms sdk shared
```

**"Cline is the engine under the hood of this demo — ProofPatch is its verification layer."**

---

## Appendix B — What `curl` people can run instead of the UI

```bash
curl -X POST http://127.0.0.1:8000/api/runs \
  -H 'Content-Type: application/json' \
  -d '{"repository":{"path":"/path/to/repo"},
       "issue":{"title":"...","repro_command":"pytest -q ..."}}'
curl http://127.0.0.1:8000/api/runs/<run_id>/report.md
```

---

*Timings assume the funded Cline API key from `.env`. Every command above emits machine-readable
exit codes too (`0`=VERIFIED, `2`=NEEDS_REVIEW, `3`=REJECTED, `4`=ERROR), so Cline or any coding
assistant can drive it.*
