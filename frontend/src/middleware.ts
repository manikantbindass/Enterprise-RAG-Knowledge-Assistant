import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
const PROTECTED = ["/dashboard", "/chat", "/documents", "/admin", "/settings"];
export function middleware(request: NextRequest) {
  // Navigation hint only. The API verifies session hashes and membership on every request.
  if (
    PROTECTED.some((path) => request.nextUrl.pathname.startsWith(path)) &&
    !request.cookies.has("rag_session")
  ) {
    return NextResponse.redirect(new URL("/", request.url));
  }
  return NextResponse.next();
}
export const config = {
  matcher: [
    "/dashboard/:path*",
    "/chat/:path*",
    "/documents/:path*",
    "/admin/:path*",
    "/settings/:path*",
  ],
};
