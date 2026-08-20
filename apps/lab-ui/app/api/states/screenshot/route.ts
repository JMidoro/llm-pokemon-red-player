import { spawn } from "child_process";
import path from "path";
import { NextResponse } from "next/server";
import { repoRoot } from "@/lib/repo";

const allowedMetadataRoots = [
  path.join(repoRoot, "research", "golden-states"),
  path.join(repoRoot, "research", "artifacts"),
  path.join(repoRoot, "research", "skill-states"),
];

type ScreenshotRequest = {
  metadataPath?: string;
};

export async function POST(request: Request) {
  const body = (await request.json()) as ScreenshotRequest;
  if (!body.metadataPath) {
    return NextResponse.json({ error: "metadataPath is required" }, { status: 400 });
  }

  const metadataPath = path.resolve(body.metadataPath);
  if (!allowedMetadataRoots.some((root) => isWithin(metadataPath, root))) {
    return NextResponse.json({ error: "metadataPath is outside allowed roots" }, { status: 403 });
  }

  try {
    const output = await captureScreenshot(metadataPath);
    return NextResponse.json({ ok: true, output });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Screenshot capture failed" },
      { status: 500 },
    );
  }
}

function captureScreenshot(metadataPath: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const python = path.join(repoRoot, ".venv", "Scripts", "python.exe");
    const script = path.join(repoRoot, "scripts", "capture_state_screenshot.py");
    const child = spawn(python, [script, metadataPath], { cwd: repoRoot });

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
        reject(new Error(stderr || stdout || `Screenshot capture exited with code ${code}`));
        return;
      }
      resolve(stdout);
    });
  });
}

function isWithin(candidate: string, parent: string): boolean {
  const relative = path.relative(parent, candidate);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}
