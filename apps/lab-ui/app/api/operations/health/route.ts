import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const operationsUrl = process.env.OPERATIONS_SERVICE_URL || "http://127.0.0.1:8766";

export async function GET() {
  try {
    const upstream = await fetch(`${operationsUrl}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(2000),
    });
    const response = NextResponse.json(await upstream.json(), { status: upstream.status });
    response.headers.set("Cache-Control", "no-store");
    response.headers.set("X-Content-Type-Options", "nosniff");
    return response;
  } catch {
    return NextResponse.json(
      { schema: "operations_health_v1", status: "offline" },
      { status: 503, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } },
    );
  }
}
