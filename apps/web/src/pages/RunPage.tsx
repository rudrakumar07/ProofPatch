import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { getDiff, getEvents, getReport, getReportMarkdown, getRun } from "../api";
import VerdictCard from "../components/VerdictCard";
import RunPanels from "./RunPanels";
import type { ProofReport, RunEvent, RunOut } from "../types";

const TERMINAL = new Set(["VERIFIED", "NEEDS_REVIEW", "REJECTED", "ERROR"]);
const SSE_TYPES = [
  "run_created",
  "run_status_changed",
  "step_started",
  "step_completed",
  "artifact_created",
  "warning",
  "run_completed",
  "run_error",
  "done",
];

export type Tab = "timeline" | "evidence" | "patch" | "tests" | "logs" | "report";

const TABS: [Tab, string][] = [
  ["timeline", "Timeline"],
  ["evidence", "Evidence"],
  ["patch", "Patch"],
  ["tests", "Generated tests"],
  ["logs", "Logs"],
  ["report", "Report"],
];

export default function RunPage() {
  const { runId = "" } = useParams();
  const [run, setRun] = useState<RunOut | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [report, setReport] = useState<ProofReport | null>(null);
  const [markdown, setMarkdown] = useState("");
  const [diff, setDiff] = useState("");
  const [tab, setTab] = useState<Tab>("timeline");
  const [error, setError] = useState<string | null>(null);
  const seqRef = useRef(0);

  function appendEvents(incoming: RunEvent[]) {
    if (!incoming.length) return;
    setEvents((previous) => {
      const known = new Set(previous.map((e) => e.sequence));
      const fresh = incoming.filter((e) => !known.has(e.sequence));
      if (fresh.length === 0) return previous;
      const merged = [...previous, ...fresh].sort((a, b) => a.sequence - b.sequence);
      seqRef.current = Math.max(...merged.map((e) => e.sequence));
      return merged;
    });
  }

  useEffect(() => {
    let cancelled = false;
    let source: EventSource | null = null;
    let poller: number | null = null;

    async function refresh() {
      try {
        const current = await getRun(runId);
        if (cancelled) return;
        setRun(current);
        if (TERMINAL.has(current.status)) {
          const [r, md, d] = await Promise.all([
            getReport(runId).catch(() => null),
            getReportMarkdown(runId).catch(() => ""),
            getDiff(runId).catch(() => ""),
          ]);
          if (cancelled) return;
          if (r) setReport(r);
          if (md) setMarkdown(md);
          if (d) setDiff(d);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    }

    void refresh();

    if (typeof EventSource !== "undefined") {
      try {
        source = new EventSource(`/api/runs/${runId}/events`);
        for (const type of SSE_TYPES) {
          source.addEventListener(type, (event) => {
            try {
              const payload = JSON.parse((event as MessageEvent).data) as RunEvent;
              if (type === "done") {
                void refresh();
                source?.close();
                return;
              }
              appendEvents([payload]);
              if (type === "run_completed" || type === "run_error") void refresh();
            } catch {
              /* ignore malformed frame */
            }
          });
        }
      } catch {
        source = null;
      }
    }

    poller = window.setInterval(async () => {
      await refresh();
      if (!source) {
        const fresh = await getEvents(runId, seqRef.current);
        appendEvents(fresh);
      }
    }, 1500);

    return () => {
      cancelled = true;
      if (poller !== null) window.clearInterval(poller);
      source?.close();
    };
  }, [runId]);

  const running = !run || !TERMINAL.has(run.status);

  return (
    <div className="page run-page">
      <div className="run-header">
        <div>
          <h1>ProofPatch Verification</h1>
          <div className="run-meta">
            <span>
              <strong>Issue:</strong>{" "}
              {run?.issue_title ?? String(report?.issue?.title ?? "…") ?? "…"}
            </span>
            <span>
              <strong>Status:</strong> {run?.status ?? "…"}
            </span>
            <span>
              <strong>Base commit:</strong> {(run?.base_commit ?? "").slice(0, 12) || "—"}
            </span>
            <span>
              <strong>Run:</strong> {runId}
            </span>
          </div>
        </div>
        <VerdictCard
          verdict={run?.verdict ?? null}
          score={run?.score ?? null}
          summary={report?.verdict_summary ?? ""}
          reasons={report?.verification?.verdict_reasons ?? []}
          running={running}
        />
      </div>

      {error && <div className="error-box">{error}</div>}

      <nav className="tabs">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            className={tab === key ? "tab active" : "tab"}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </nav>

      <section className="panel">
        <RunPanels
          tab={tab}
          events={events}
          report={report}
          diff={diff}
          markdown={markdown}
          running={running}
        />
      </section>
    </div>
  );
}
