import path from "path";
import { NextResponse } from "next/server";
import { repoRoot } from "@/lib/repo";

const directorPlayerUrl = process.env.DIRECTOR_PLAYER_URL || "http://127.0.0.1:8765";
const allowedStateRoot = path.join(repoRoot, "research");

type DirectorPlayerRequest = {
  action?: "execute_skill" | "load_state" | "manual_input" | "capture_interpretation" | "diagnostic_mode";
  skillId?: string;
  args?: Record<string, unknown>;
  statePath?: string;
  button?: string;
  title?: string;
  description?: string;
  enabled?: boolean;
};

export async function GET() {
  return proxyJson(`${directorPlayerUrl}/status`, { method: "GET" });
}

export async function POST(request: Request) {
  const body = (await request.json()) as DirectorPlayerRequest;
  if (body.action === "load_state") {
    if (!body.statePath) {
      return NextResponse.json({ error: "statePath is required" }, { status: 400 });
    }
    const statePath = path.resolve(repoRoot, body.statePath);
    if (!isWithin(statePath, allowedStateRoot)) {
      return NextResponse.json({ error: "statePath is outside the research workspace" }, { status: 403 });
    }
    return proxyJson(`${directorPlayerUrl}/load-state`, {
      method: "POST",
      body: JSON.stringify({ statePath }),
    });
  }

  if (body.action === "manual_input") {
    if (!body.button) {
      return NextResponse.json({ error: "button is required" }, { status: 400 });
    }
    return proxyJson(`${directorPlayerUrl}/manual-input`, {
      method: "POST",
      body: JSON.stringify({ button: body.button }),
    });
  }

  if (body.action === "diagnostic_mode") {
    return proxyJson(`${directorPlayerUrl}/diagnostic-mode`, {
      method: "POST",
      body: JSON.stringify({ enabled: Boolean(body.enabled) }),
    });
  }

  if (body.action === "capture_interpretation") {
    if (!body.title || !body.title.trim()) {
      return NextResponse.json({ error: "title is required" }, { status: 400 });
    }
    return proxyJson(`${directorPlayerUrl}/capture-interpretation`, {
      method: "POST",
      body: JSON.stringify({ title: body.title, description: body.description || "" }),
    });
  }

  if (!body.skillId) {
    return NextResponse.json({ error: "skillId is required" }, { status: 400 });
  }
  return proxyJson(`${directorPlayerUrl}/skill`, {
    method: "POST",
    body: JSON.stringify({ skillId: body.skillId, args: body.args || {} }),
  });
}

function isWithin(candidate: string, parent: string): boolean {
  const relative = path.relative(parent, candidate);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

async function proxyJson(url: string, init: RequestInit) {
  try {
    const response = await fetch(url, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init.headers || {}),
      },
      cache: "no-store",
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Director player is not reachable",
        offline: true,
        directorPlayerUrl,
      },
      { status: 503 },
    );
  }
}
