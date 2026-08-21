import { spawn } from "child_process";
import { existsSync } from "fs";
import path from "path";
import { NextResponse } from "next/server";
import { repoRoot } from "@/lib/repo";

export const runtime = "nodejs";

type LlmPlayerRequest = {
  goal?: unknown;
  provider?: unknown;
  model?: unknown;
  reasoningEffort?: unknown;
  messages?: unknown;
  tick?: unknown;
  messageLimit?: unknown;
};

type RuntimeResult = {
  status?: string;
  error?: string;
  [key: string]: unknown;
};

type CanonicalRuntimeInput = {
  goal: string;
  provider?: "openai-responses" | "lmstudio-chat";
  model?: string;
  reasoningEffort?: string;
  messages?: unknown[];
  tick?: number;
  messageLimit?: number;
};

export async function POST(request: Request) {
  let body: LlmPlayerRequest;
  try {
    body = (await request.json()) as LlmPlayerRequest;
  } catch {
    return NextResponse.json({ error: "Request body must be valid JSON." }, { status: 400 });
  }
  if (typeof body.goal !== "string" || !body.goal.trim()) {
    return NextResponse.json({ error: "goal is required" }, { status: 400 });
  }
  if (
    body.provider !== undefined &&
    body.provider !== "openai-responses" &&
    body.provider !== "lmstudio-chat"
  ) {
    return NextResponse.json({ error: "unsupported provider" }, { status: 400 });
  }

  const canonicalInput: CanonicalRuntimeInput = {
    goal: body.goal.trim(),
    provider: body.provider,
    model: typeof body.model === "string" ? body.model : undefined,
    reasoningEffort:
      typeof body.reasoningEffort === "string" ? body.reasoningEffort : undefined,
    messages: Array.isArray(body.messages) ? body.messages : undefined,
    tick: typeof body.tick === "number" ? body.tick : undefined,
    messageLimit: typeof body.messageLimit === "number" ? body.messageLimit : undefined,
  };

  try {
    const result = await runCanonicalDirector(canonicalInput);
    const status = result.status === "error" ? 502 : 200;
    return NextResponse.json(result, { status });
  } catch (error) {
    return NextResponse.json(
      {
        schema: "director_segment_run_v1",
        status: "error",
        error: error instanceof Error ? error.message : "Canonical Director runtime failed.",
      },
      { status: 502 },
    );
  }
}

function runCanonicalDirector(body: CanonicalRuntimeInput): Promise<RuntimeResult> {
  const scriptPath = path.join(repoRoot, "scripts", "run_director_tick.py");
  const configuredPython = process.env.DIRECTOR_RUNTIME_PYTHON;
  const venvPython =
    process.platform === "win32"
      ? path.join(repoRoot, ".venv", "Scripts", "python.exe")
      : path.join(repoRoot, ".venv", "bin", "python");
  const fallbackPython = process.platform === "win32" ? "python" : "python3";
  const python = configuredPython || (existsSync(venvPython) ? venvPython : fallbackPython);
  const timeoutMs = boundedTimeout(process.env.DIRECTOR_RUNTIME_TIMEOUT_MS);

  return new Promise((resolve, reject) => {
    const child = spawn(python, [scriptPath], {
      cwd: repoRoot,
      env: process.env,
      windowsHide: true,
      stdio: ["pipe", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    let settled = false;
    const timeout = setTimeout(() => {
      child.kill();
      finishReject(new Error(`Canonical Director runtime timed out after ${timeoutMs}ms.`));
    }, timeoutMs);

    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk: string) => {
      stderr += chunk;
    });
    child.on("error", (error) => finishReject(error));
    child.on("close", () => {
      try {
        const parsed = JSON.parse(stdout.trim()) as RuntimeResult;
        finishResolve(parsed);
      } catch {
        finishReject(
          new Error(stderr.trim() || "Canonical Director runtime returned invalid JSON."),
        );
      }
    });
    child.stdin.end(JSON.stringify(body));

    function finishResolve(result: RuntimeResult) {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      resolve(result);
    }

    function finishReject(error: Error) {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      reject(error);
    }
  });
}

function boundedTimeout(value: string | undefined): number {
  const parsed = Number(value || 900_000);
  if (!Number.isFinite(parsed)) return 900_000;
  return Math.max(10_000, Math.min(Math.floor(parsed), 1_800_000));
}
