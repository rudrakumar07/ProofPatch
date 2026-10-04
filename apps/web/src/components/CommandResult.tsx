import type { RunEvent } from "../types";

const MARK: Record<string, string> = {
  PASSED: "✓",
  FAILED: "✗",
  SKIPPED: "–",
  ERROR: "!",
};

/** A single log line rendered in the run's event stream. */
export default function CommandResult({ event }: { event: RunEvent }) {
  const mark = MARK[event.status ?? ""] ?? "·";
  const time = new Date(event.timestamp).toLocaleTimeString();
  return (
    <div className={`log-line log-${(event.status ?? "info").toLowerCase()}`}>
      <span className="log-time">{time}</span>
      <span className="log-mark">{mark}</span>
      <span className="log-step">{event.step ?? event.type}</span>
      <span className="log-message">{event.message}</span>
    </div>
  );
}
