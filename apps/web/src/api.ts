/** Minimal typed API client. All URLs are relative so the Vite dev proxy and
 * the production single-server deployment both work unchanged. */

import type { ProofReport, RunCreateRequest, RunEvent, RunOut } from "./types";

async function jsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export async function createRun(request: RunCreateRequest): Promise<{ run_id: string; status: string }> {
  const response = await fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  return jsonOrThrow(response);
}

export async function getRun(runId: string): Promise<RunOut> {
  const response = await fetch(`/api/runs/${runId}`);
  return jsonOrThrow(response);
}

export async function listRuns(): Promise<RunOut[]> {
  const response = await fetch("/api/runs");
  return jsonOrThrow(response);
}

export async function getReport(runId: string): Promise<ProofReport> {
  const response = await fetch(`/api/runs/${runId}/report`);
  return jsonOrThrow(response);
}

export async function getDiff(runId: string): Promise<string> {
  const response = await fetch(`/api/runs/${runId}/diff`);
  if (!response.ok) throw new Error(`${response.status}`);
  return response.text();
}

export async function getReportMarkdown(runId: string): Promise<string> {
  const response = await fetch(`/api/runs/${runId}/report.md`);
  if (!response.ok) throw new Error(`${response.status}`);
  return response.text();
}

export async function getEvents(runId: string, afterSequence = 0): Promise<RunEvent[]> {
  // Non-streaming fallback used when EventSource is unavailable.
  const response = await fetch(`/api/runs/${runId}/events.json?after=${afterSequence}`);
  if (!response.ok) return [];
  return (await response.json()) as RunEvent[];
}
