import type { Verdict } from "../types";

interface Props {
  verdict: Verdict | null;
  score: number | null;
  summary: string;
  reasons: string[];
  running: boolean;
}

const HEADLINES: Record<Verdict, string> = {
  VERIFIED: "Ready for Review",
  NEEDS_REVIEW: "Needs Review",
  REJECTED: "Rejected",
  ERROR: "Verification Error",
};

export default function VerdictCard({ verdict, score, summary, reasons, running }: Props) {
  if (running || !verdict) {
    return (
      <div className="verdict-card verdict-running">
        <div className="verdict-title">Verification in progress</div>
        <div className="verdict-sub">Evidence is being collected…</div>
      </div>
    );
  }
  return (
    <div className={`verdict-card verdict-${verdict.toLowerCase()}`}>
      <div className="verdict-title">{HEADLINES[verdict]}</div>
      <div className="verdict-score">
        Evidence Score: <strong>{score ?? 0} / 100</strong>
      </div>
      <div className="verdict-verdict">{verdict}</div>
      <div className="verdict-sub">{summary}</div>
      {reasons.length > 0 && (
        <ul className="verdict-reasons">
          {reasons.map((reason, index) => (
            <li key={index}>{reason}</li>
          ))}
        </ul>
      )}
      <p className="verdict-note">
        The evidence score is not a calibrated probability of correctness.
      </p>
    </div>
  );
}
