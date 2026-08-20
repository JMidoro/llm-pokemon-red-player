import { spawn } from "child_process";
import path from "path";
import { NextResponse } from "next/server";
import { repoRoot } from "@/lib/repo";

type DirectorRequest = {
  directive?: string;
  stateSummary?: string;
  objective?: string;
  mode?: "auto" | "offline" | "openai";
};

export async function POST(request: Request) {
  const body = (await request.json()) as DirectorRequest;
  if (!body.directive || !body.stateSummary || !body.objective) {
    return NextResponse.json({ error: "directive, stateSummary, and objective are required" }, { status: 400 });
  }

  try {
    const verdict = await classifyDirective({
      directive: body.directive,
      stateSummary: body.stateSummary,
      objective: body.objective,
      mode: body.mode ?? "auto",
    });
    return NextResponse.json(verdict);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Directive classification failed" },
      { status: 500 },
    );
  }
}

function classifyDirective(input: Required<DirectorRequest>): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const python = path.join(repoRoot, ".venv", "Scripts", "python.exe");
    const script = path.join(repoRoot, "scripts", "classify_directive.py");
    const child = spawn(
      python,
      [
        script,
        input.directive,
        "--state-summary",
        input.stateSummary,
        "--objective",
        input.objective,
        "--mode",
        input.mode,
      ],
      { cwd: repoRoot },
    );

    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(stderr || stdout || `Classifier exited with code ${code}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch (error) {
        reject(error);
      }
    });
  });
}
