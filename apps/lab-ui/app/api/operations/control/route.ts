import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

const operationsUrl = process.env.OPERATIONS_SERVICE_URL || "http://127.0.0.1:8766";
const actions = new Set(["pause", "resume", "stop_after_action", "emergency_stop"]);

export async function POST(request: NextRequest) {
  const origin = request.headers.get("origin");
  const expectedHost = request.headers.get("x-forwarded-host") || request.headers.get("host");
  let sameOrigin = false;
  try {
    sameOrigin = Boolean(origin && expectedHost && new URL(origin).host === expectedHost);
  } catch {
    sameOrigin = false;
  }
  if (!sameOrigin) {
    return secureJson({ error: "Same-origin request required." }, 403);
  }
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
    return secureJson({ error: "JSON request required." }, 415);
  }
  let body: { action?: string };
  try {
    body = await request.json();
  } catch {
    return secureJson({ error: "Valid JSON request required." }, 400);
  }
  if (!body.action || !actions.has(body.action)) {
    return secureJson({ error: "Unsupported control action." }, 400);
  }
  try {
    const response = await fetch(`${operationsUrl}/control`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: body.action, source: "remote_operations_ui" }),
      cache: "no-store",
      signal: AbortSignal.timeout(2500),
    });
    return secureJson(await response.json(), response.status);
  } catch {
    return secureJson({ error: "The local control service is unavailable; the existing run state was not changed." }, 503);
  }
}

function secureJson(body: unknown, status: number) {
  const response = NextResponse.json(body, { status });
  response.headers.set("Cache-Control", "no-store");
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("Referrer-Policy", "no-referrer");
  return response;
}
