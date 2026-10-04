import type { RunEvent } from "../types";

export interface TimelineStep {
  key: string;
  label: string;
}

/** Canonical order of the verification story shown to a reviewer. */
export const TIMELINE_STEPS: TimelineStep[] = [
  { key: "repository_prepared", label: "Repository prepared" },
  { key: "baseline_reproduction", label: "Baseline issue reproduction" },
  { key: "baseline_existing_tests", label: "Baseline regression suite" },
  { key: "root_cause_analysis", label: "Root-cause analysis" },
  { key: "patch_generated", label: "Patch generated" },
  { key: "tests_generated", label: "Verification tests generated" },
  { key: "baseline_generated_tests", label: "Baseline verification tests" },
  { key: "candidate_patch_applied", label: "Candidate patch applied" },
  { key: "candidate_reproduction", label: "Candidate issue reproduction" },
  { key: "candidate_generated_tests", label: "Candidate verification tests" },
  { key: "candidate_existing_tests", label: "Regression suite" },
  { key: "candidate_static", label: "Static analysis" },
  { key: "proof_report", label: "Proof report" },
];

type Status = "PENDING" | "RUNNING" | "PASSED" | "FAILED" | "SKIPPED";

function statusFor(events: RunEvent[], stepKey: string): { status: Status; message: string } {
  const completed = events.filter((e) => e.type === "step_completed" && e.step === stepKey);
  if (completed.length > 0) {
    const last = completed[completed.length - 1];
    return { status: (last.status as Status) ?? "PASSED", message: last.message };
  }
  const started = events.find((e) => e.type === "step_started" && e.step === stepKey);
  if (started) return { status: "RUNNING", message: started.message };
  return { status: "PENDING", message: "Waiting" };
}

const MARK: Record<Status, string> = {
  PENDING: "○",
  RUNNING: "◔",
  PASSED: "✓",
  FAILED: "✗",
  SKIPPED: "–",
};

export default function RunTimeline({ events }: { events: RunEvent[] }) {
  return (
    <ol className="timeline">
      {TIMELINE_STEPS.map((step) => {
        const { status, message } = statusFor(events, step.key);
        return (
          <li key={step.key} className={`timeline-item status-${status.toLowerCase()}`}>
            <span className="timeline-mark">{MARK[status]}</span>
            <span className="timeline-label">{step.label}</span>
            <span className="timeline-status">{status}</span>
            <span className="timeline-message">{message}</span>
          </li>
        );
      })}
    </ol>
  );
}
