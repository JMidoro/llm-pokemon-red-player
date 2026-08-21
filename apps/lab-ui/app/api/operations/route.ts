import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const operationsUrl = process.env.OPERATIONS_SERVICE_URL || "http://127.0.0.1:8766";

export async function GET() {
  try {
    const response = await fetch(`${operationsUrl}/snapshot`, { cache: "no-store", signal: AbortSignal.timeout(2500) });
    const body = await response.json();
    return secureJson(body, response.status);
  } catch {
    return secureJson({ error: "Local operations services are unavailable.", offline: true }, 503);
  }
}

function secureJson(body: unknown, status: number) {
  const response = NextResponse.json(body, { status });
  response.headers.set("Cache-Control", "no-store");
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("Referrer-Policy", "no-referrer");
  return response;
}
