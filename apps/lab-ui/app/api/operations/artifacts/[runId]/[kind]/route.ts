import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const operationsUrl = process.env.OPERATIONS_SERVICE_URL || "http://127.0.0.1:8766";
const runIdPattern = /^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/;
const artifactKinds = new Set(["screenshot", "video", "summary"]);

export async function GET(request: NextRequest, context: { params: Promise<{ runId: string; kind: string }> }) {
  const { runId, kind } = await context.params;
  if (!runIdPattern.test(runId) || !artifactKinds.has(kind)) {
    return NextResponse.json({ error: "Artifact not found." }, { status: 404 });
  }
  try {
    const headers = new Headers();
    const range = request.headers.get("range");
    if (range) headers.set("range", range);
    const upstream = await fetch(`${operationsUrl}/artifacts/${encodeURIComponent(runId)}/${kind}`, {
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
    });
    const responseHeaders = new Headers({
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
      "Content-Security-Policy": "default-src 'none'; sandbox",
      "Referrer-Policy": "no-referrer",
    });
    for (const name of ["content-type", "content-length", "content-range", "accept-ranges", "content-disposition"]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch {
    return NextResponse.json({ error: "Artifact is unavailable." }, { status: 503 });
  }
}
