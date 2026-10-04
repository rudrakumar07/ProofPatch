#!/usr/bin/env node
/**
 * ProofPatch <-> Cline SDK bridge.
 *
 * ProofPatch's engine is Python and the Cline SDK is TypeScript, so this small
 * Node process is the seam between them. It:
 *
 *   1. reads one JSON request from stdin
 *   2. runs a single-shot Cline SDK agent turn (no tools, so the agent can only
 *      return text -- it can never edit files or run commands in your repo)
 *   3. writes one JSON response to stdout
 *
 * Request  (stdin):  { systemPrompt, userPrompt, providerId, modelId,
 *                      baseUrl?, apiKey?, maxIterations?, cwd?, timeoutMs? }
 * Response (stdout): { ok: true, text, usage, iterations, eventCount }
 *                    { ok: false, error, detail }
 *
 * The process exits 0 on success and 1 on failure. Diagnostics go to stderr so
 * stdout stays parseable as a single JSON document.
 */

import process from "node:process";

function readStdin() {
  return new Promise((resolve, reject) => {
    let raw = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      raw += chunk;
    });
    process.stdin.on("end", () => resolve(raw));
    process.stdin.on("error", reject);
  });
}

function fail(error, detail) {
  process.stdout.write(JSON.stringify({ ok: false, error: String(error), detail: detail ? String(detail) : undefined }));
  process.exit(1);
}

async function main() {
  const raw = await readStdin();
  if (!raw.trim()) {
    fail("Empty request", "The bridge expects a JSON request on stdin.");
    return;
  }

  let request;
  try {
    request = JSON.parse(raw);
  } catch (error) {
    fail("Invalid JSON request", error instanceof Error ? error.message : error);
    return;
  }

  const {
    systemPrompt = "",
    userPrompt = "",
    providerId = "cline",
    modelId,
    baseUrl,
    apiKey,
    maxIterations = 1,
    cwd,
    timeoutMs = 180000,
  } = request;

  if (!userPrompt) {
    fail("Missing userPrompt", "userPrompt is required.");
    return;
  }

  let Agent;
  try {
    ({ Agent } = await import("@cline/sdk"));
  } catch (error) {
    fail(
      "Cline SDK is not installed",
      `${error instanceof Error ? error.message : error}. Run 'npm install' in packages/cline-bridge.`,
    );
    return;
  }

  const config = { providerId, maxIterations, tools: [] };
  if (modelId) config.modelId = modelId;
  if (baseUrl) config.baseUrl = baseUrl;
  if (apiKey) config.apiKey = apiKey;
  if (systemPrompt) config.systemPrompt = systemPrompt;
  if (cwd) config.cwd = cwd;

  const agent = new Agent(config);

  const deltas = [];
  let eventCount = 0;
  let lastError = null;
  let runStatus = null;

  agent.subscribe((event) => {
    eventCount += 1;
    switch (event?.type) {
      case "assistant-text-delta":
        if (event.text) deltas.push(event.text);
        break;
      case "run-finished":
        runStatus = event.result?.status ?? null;
        break;
      case "run-failed":
        lastError = event.error?.message ?? String(event.error ?? "unknown agent error");
        runStatus = "failed";
        break;
      default:
        break;
    }
  });

  const timer = setTimeout(() => {
    process.stderr.write(`[bridge] run exceeded ${timeoutMs}ms; aborting\n`);
    process.exit(1);
  }, timeoutMs);
  timer.unref?.();

  let result;
  try {
    result = await agent.run(userPrompt);
  } catch (error) {
    fail(
      "Agent run failed",
      error instanceof Error ? `${error.message}\n${error.stack ?? ""}` : error,
    );
    return;
  }

  const text = result?.outputText ?? result?.text ?? deltas.join("");
  const usage = result?.usage ?? null;
  const status = result?.status ?? runStatus;

  if (!text || !text.trim()) {
    fail(
      result?.error?.message ?? lastError ?? "Agent returned no text",
      status ? `status=${status}` : undefined,
    );
    return;
  }

  process.stdout.write(
    JSON.stringify({
      ok: true,
      text,
      usage,
      status,
      iterations: typeof result?.iterations === "number" ? result.iterations : undefined,
      eventCount,
      streamedChars: deltas.join("").length,
    }),
  );
}

main().catch((error) => {
  fail("Unhandled bridge error", error instanceof Error ? `${error.message}\n${error.stack ?? ""}` : error);
});
