import { NextRequest, NextResponse } from "next/server";

export function proxy(request: NextRequest) {
  if (process.env.POKEMON_OPERATIONS_REMOTE_ONLY !== "1") {
    return NextResponse.next();
  }

  const path = request.nextUrl.pathname;
  if (path === "/") {
    return NextResponse.redirect(new URL("/operations", request.url));
  }
  if (
    path === "/operations" ||
    path.startsWith("/api/operations/") ||
    path === "/api/operations" ||
    path.startsWith("/_next/static/") ||
    path === "/_next/webpack-hmr" ||
    path.startsWith("/_next/development/") ||
    path === "/favicon.ico"
  ) {
    const response = NextResponse.next();
    response.headers.set("X-Frame-Options", "DENY");
    response.headers.set("X-Content-Type-Options", "nosniff");
    response.headers.set("Referrer-Policy", "no-referrer");
    response.headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
    return response;
  }

  return new NextResponse("Not found", {
    status: 404,
    headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
  });
}
