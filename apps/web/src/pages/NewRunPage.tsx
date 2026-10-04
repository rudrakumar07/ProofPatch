import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createRun, listRuns } from "../api";
import type { RunOut } from "../types";

const FIELD_STORAGE = "proofpatch:lastRequest";

interface SavedForm {
  repo: string;
  title: string;
  description: string;
  errorLog: string;
  expected: string;
  repro: string;
  fullTest: string;
}

const DEFAULTS: SavedForm = {
  repo: "",
  title: "Payment allowed at exact session expiry",
  description:
    "A payment session should no longer be usable once its expiry timestamp is reached. Currently a payment attempted exactly at expires_at is accepted.",
  errorLog: "",
  expected: "now >= expires_at should be treated as expired",
  repro: "",
  fullTest: "",
};

export default function NewRunPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState<SavedForm>(() => {
    try {
      const raw = localStorage.getItem(FIELD_STORAGE);
      if (raw) return { ...DEFAULTS, ...(JSON.parse(raw) as Partial<SavedForm>) };
    } catch {
      /* ignore */
    }
    return DEFAULTS;
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [recent, setRecent] = useState<RunOut[]>([]);

  useEffect(() => {
    listRuns()
      .then(setRecent)
      .catch(() => setRecent([]));
  }, []);

  function update<K extends keyof SavedForm>(key: K, value: string) {
    setForm((previous) => {
      const next = { ...previous, [key]: value };
      localStorage.setItem(FIELD_STORAGE, JSON.stringify(next));
      return next;
    });
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await createRun({
        repository: { path: form.repo.trim() },
        issue: {
          title: form.title.trim() || "Reported issue",
          description: form.description,
          error_log: form.errorLog || null,
          expected_behavior: form.expected || null,
          repro_command: form.repro || null,
        },
        verification: {
          full_test_command: form.fullTest || null,
          timeout_seconds: 120,
        },
      });
      navigate(`/runs/${created.run_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <h1>New Verification Run</h1>
      <p className="muted">
        ProofPatch inspects the repository, proposes a fix, generates independent tests, and shows
        evidence for or against the patch.
      </p>

      <form className="run-form" onSubmit={onSubmit}>
        <label>
          Repository path (Git, local, must be clean)
          <input
            required
            value={form.repo}
            onChange={(e) => update("repo", e.target.value)}
            placeholder="/absolute/path/to/repo"
          />
        </label>

        <label>
          Issue title
          <input required value={form.title} onChange={(e) => update("title", e.target.value)} />
        </label>

        <label>
          Issue description
          <textarea
            rows={5}
            value={form.description}
            onChange={(e) => update("description", e.target.value)}
          />
        </label>

        <label>
          Error log / stack trace <span className="optional">(optional)</span>
          <textarea
            rows={4}
            value={form.errorLog}
            onChange={(e) => update("errorLog", e.target.value)}
          />
        </label>

        <label>
          Expected behavior <span className="optional">(optional)</span>
          <input value={form.expected} onChange={(e) => update("expected", e.target.value)} />
        </label>

        <label>
          Reproduction command <span className="optional">(strongly recommended)</span>
          <input
            value={form.repro}
            onChange={(e) => update("repro", e.target.value)}
            placeholder="pytest -q tests/test_session.py::test_payment_rejected_at_exact_expiry"
          />
        </label>

        <label>
          Full test command <span className="optional">(advanced, auto-detected if empty)</span>
          <input
            value={form.fullTest}
            onChange={(e) => update("fullTest", e.target.value)}
            placeholder="pytest -q --junitxml=.proofpatch_pytest.xml"
          />
        </label>

        {error && <div className="error-box">{error}</div>}

        <button type="submit" disabled={busy}>
          {busy ? "Starting…" : "Start Verification"}
        </button>
      </form>

      <section className="recent">
        <h2>Recent runs</h2>
        {recent.length === 0 ? (
          <p className="muted">No runs yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Run</th>
                <th>Issue</th>
                <th>Status</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((run) => (
                <tr key={run.run_id}>
                  <td>
                    <Link to={`/runs/${run.run_id}`}>{run.run_id.slice(0, 14)}…</Link>
                  </td>
                  <td>{run.issue_title}</td>
                  <td>
                    <span className={`badge badge-${run.status.toLowerCase()}`}>{run.status}</span>
                  </td>
                  <td>{run.score ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
