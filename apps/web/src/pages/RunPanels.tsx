import CommandResult from "../components/CommandResult";
import DiffViewer from "../components/DiffViewer";
import EvidenceChecklist from "../components/EvidenceChecklist";
import RunTimeline from "../components/RunTimeline";
import type { ProofReport, RunEvent } from "../types";
import type { Tab } from "./RunPage";

interface Props {
  tab: Tab;
  events: RunEvent[];
  report: ProofReport | null;
  diff: string;
  markdown: string;
  running: boolean;
}

function RootCause({ report }: { report: ProofReport }) {
  const rc = report.root_cause as Record<string, unknown> | null;
  if (!rc) return null;
  return (
    <div className="root-cause">
      <h3>Root cause analysis</h3>
      <p>{String(rc.summary ?? "")}</p>
      <p className="muted">
        <strong>Confidence:</strong> {String(rc.confidence ?? "—")} · <strong>Files:</strong>{" "}
        {((rc.suspected_files as string[]) ?? []).join(", ") || "—"} · <strong>Symbols:</strong>{" "}
        {((rc.relevant_symbols as string[]) ?? []).join(", ") || "—"}
      </p>
      <ul>
        {((rc.reasoning_summary as string[]) ?? []).map((line, index) => (
          <li key={index}>{line}</li>
        ))}
      </ul>
    </div>
  );
}

export default function RunPanels({ tab, events, report, diff, markdown, running }: Props) {
  if (tab === "timeline") {
    if (events.length === 0) {
      return <p className="muted">Waiting for the first events…</p>;
    }
    return <RunTimeline events={events} />;
  }

  if (tab === "evidence") {
    const verification = report?.verification;
    return (
      <>
        <EvidenceChecklist evidence={verification?.evidence ?? []} />
        {verification && verification.limitations.length > 0 && (
          <div className="limitations">
            <h3>Limitations</h3>
            <ul>
              {verification.limitations.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </div>
        )}
      </>
    );
  }

  if (tab === "logs") {
    return (
      <div className="log">
        {events.length === 0 && <p className="muted">No events yet.</p>}
        {events.map((event) => (
          <CommandResult key={event.sequence} event={event} />
        ))}
      </div>
    );
  }

  if (!report) {
    return <p className="muted">{running ? "Waiting for the report…" : "Report not available."}</p>;
  }

  if (tab === "patch") {
    const patch = report.patch as Record<string, unknown> | null;
    if (!patch) return <p className="muted">No patch was produced.</p>;
    const risks = (patch.risks as string[]) ?? [];
    return (
      <div className="stack">
        <h3>Candidate patch</h3>
        <p>{String(patch.summary ?? "")}</p>
        <p className="muted">{String(patch.why_it_should_work ?? "")}</p>
        <p>
          <strong>Files changed:</strong> {((patch.affected_files as string[]) ?? []).join(", ")}
        </p>
        <DiffViewer
          diff={diff || String(patch.unified_diff ?? "")}
          path={String(patch.diff_artifact ?? "candidate.diff")}
        />
        {risks.length > 0 && (
          <div>
            <strong>Risk notes</strong>
            <ul>
              {risks.map((risk, index) => (
                <li key={index}>{risk}</li>
              ))}
            </ul>
          </div>
        )}
        <RootCause report={report} />
      </div>
    );
  }

  if (tab === "tests") {
    const gen = report.generated_tests as Record<string, unknown> | null;
    const verification = report.verification;
    if (!gen) return <p className="muted">No generated verification tests.</p>;
    const newRegressions = (report.regression.new_regressions as string[]) ?? [];
    const newFindings = (report.static.new_findings as string[]) ?? [];
    return (
      <div className="stack">
        <h3>Generated verification tests</h3>
        <p>
          <strong>Manifest digest:</strong> <code>{String(gen.manifest_digest ?? "—")}</code>
        </p>
        <p>
          <strong>Files:</strong> {((gen.files as string[]) ?? []).join(", ")}
        </p>
        <div className="split">
          <div className="card">
            <h4>Baseline outcomes</h4>
            <p>{String(gen.baseline_outcomes ?? "not run")}</p>
          </div>
          <div className="card">
            <h4>Candidate outcomes</h4>
            <p>{String(gen.candidate_outcomes ?? "not run")}</p>
          </div>
        </div>
        <h4>Scenarios</h4>
        <ul>
          {((gen.scenarios as string[]) ?? []).map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
        <h4>Existing regression suite</h4>
        <p>
          <strong>Baseline failures:</strong>{" "}
          {JSON.stringify(report.regression.baseline_failures ?? "not run")}
        </p>
        <p>
          <strong>Candidate failures:</strong>{" "}
          {JSON.stringify(report.regression.candidate_failures ?? "not run")}
        </p>
        <p>
          <strong>New regressions:</strong> {newRegressions.join(", ") || "none"}
        </p>
        <h4>Static / syntax verification</h4>
        <p>
          <strong>New findings:</strong> {newFindings.join(", ") || "none"}
        </p>
        <p className="muted">
          Issue reproduced: {String(verification.issue_reproduced)} · Generated tests fail on
          baseline: {String(verification.generated_tests_fail_on_baseline)} · Pass on candidate:{" "}
          {String(verification.generated_tests_pass_on_candidate)}
        </p>
      </div>
    );
  }

  return (
    <div className="stack">
      <h3>Proof report (Markdown)</h3>
      <pre className="report-markdown">{markdown || "Report not available yet."}</pre>
      <p className="muted">
        Artifact directory: <code>{report.artifact_dir}</code>
      </p>
    </div>
  );
}
