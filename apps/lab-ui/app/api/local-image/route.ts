import { promises as fs } from "fs";
import path from "path";
import { NextResponse } from "next/server";
import { repoRoot } from "@/lib/repo";

const allowedRoots = [
  path.join(repoRoot, "research", "golden-states", "local"),
  path.join(repoRoot, "research", "skill-states", "local"),
  path.join(repoRoot, "research", "artifacts"),
];

export async function GET(request: Request) {
  const url = new URL(request.url);
  const requested = url.searchParams.get("path");
  if (!requested) {
    return NextResponse.json({ error: "path is required" }, { status: 400 });
  }

  const absolutePath = path.resolve(requested);
  if (!allowedRoots.some((root) => isWithin(absolutePath, root))) {
    return NextResponse.json({ error: "path is outside allowed image roots" }, { status: 403 });
  }
  if (!absolutePath.toLowerCase().endsWith(".png")) {
    return NextResponse.json({ error: "only PNG screenshots are supported" }, { status: 400 });
  }

  try {
    const bytes = await fs.readFile(absolutePath);
    return new Response(bytes, {
      headers: {
        "Content-Type": "image/png",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json({ error: "image not found" }, { status: 404 });
  }
}

function isWithin(candidate: string, parent: string): boolean {
  const relative = path.relative(parent, candidate);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}
