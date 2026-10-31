import { NextResponse, type NextRequest } from "next/server";

// Password gate for hosted deployments. Set SITE_PASSWORD (and optionally SITE_USERNAME)
// on the web service; leave it unset for local use. It also protects /api, which the
// frontend proxies to the private backend.
function safeEqual(a: string, b: string) {
  let diff = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  }
  return diff === 0;
}

export function proxy(request: NextRequest) {
  const password = process.env.SITE_PASSWORD;
  if (!password) return NextResponse.next();
  const username = process.env.SITE_USERNAME || "privacytwin";
  const header = request.headers.get("authorization") || "";
  if (header.startsWith("Basic ")) {
    try {
      const decoded = atob(header.slice(6));
      const split = decoded.indexOf(":");
      if (
        split >= 0 &&
        safeEqual(decoded.slice(0, split), username) &&
        safeEqual(decoded.slice(split + 1), password)
      ) {
        return NextResponse.next();
      }
    } catch {
      // Malformed header: fall through to the challenge.
    }
  }
  return new NextResponse("Authentication required", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="PrivacyTwin", charset="UTF-8"' },
  });
}

export const config = {
  // /api/health stays open for the host's health check (it returns only status/version).
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/health$).*)"],
};
