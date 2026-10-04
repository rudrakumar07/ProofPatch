/** Shared API types mirroring the ProofPatch API responses. */

export type Verdict = "VERIFIED" | "NEEDS_REVIEW" | "REJECTED" | "ERROR";

export type EvidenceStatus = "pass" | "fail" | "skip" | "error";

export interface RunOut {
  run_id: string;
  status: string;
  verdict: Verdict | null;
  score: number | null;
  issue_title: string;
  repo_path: string;
  base_commit: string | null;
  repro_command: string | null;
  current_step: string | null;
  created_at: string | null;
  updated_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  artifact_dir: string;
}

export interface RunEvent {
  sequence: number;
  timestamp: string;
  type: string;
  step: string | null;
  status: string | null;
  message: string;
  payload: Record<string, unknown>;
}

export interface EvidenceItem {
  key: string;
  title: string;
  status: EvidenceStatus;
  weight: number;
  details: string;
  artifact_refs?: string[];
}

export interface VerificationResult {
  issue_reproduced: boolean | null;
  generated_tests_fail_on_baseline: boolean | null;
  generated_tests_pass_on_candidate: boolean | null;
  repro_passes_on_candidate: boolean | null;
  new_regressions: string[];
  static_new_findings: string[];
  evidence: EvidenceItem[];
  score: number;
  verdict: Verdict;
  verdict_reasons: string[];
  limitations: string[];
}

export interface ProofReport {
  run_id: string;
  repository: Record<string, unknown>;
  issue: Record<string, unknown>;
  status: string;
  verdict: Verdict;
  evidence_score: number;
  verdict_summary: string;
  reproducibility: Record<string, unknown>;
  root_cause: Record<string, unknown> | null;
  patch: Record<string, unknown> | null;
  generated_tests: Record<string, unknown> | null;
  issue_evidence: Record<string, unknown>;
  regression: Record<string, unknown>;
  static: Record<string, unknown>;
  verification: VerificationResult;
  limitations: string[];
  started_at: string | null;
  completed_at: string | null;
  artifact_dir: string;
}

export interface RunCreateRequest {
  repository: { path: string; ref?: string | null };
  issue: {
    title: string;
    description: string;
    error_log?: string | null;
    expected_behavior?: string | null;
    repro_command?: string | null;
  };
  verification?: {
    full_test_command?: string | null;
    timeout_seconds?: number;
  };
}
