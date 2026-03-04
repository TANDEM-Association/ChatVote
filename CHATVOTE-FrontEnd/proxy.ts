import { NextResponse } from "next/server";
import { type NextRequest } from "next/server";

import { TENANT_ID_HEADER } from "@lib/constants";

export async function proxy(request: NextRequest) {
  const budgetSpent = process.env.BUDGET_SPENT === "true";

  if (budgetSpent) {
    return NextResponse.redirect(new URL("/budget-spent", request.url));
  }

  const tenantIdSearchParam = request.nextUrl.searchParams.get("tenant_id");

  if (tenantIdSearchParam) {
    const requestHeaders = new Headers(request.headers);
    requestHeaders.set(TENANT_ID_HEADER, tenantIdSearchParam);

    return NextResponse.next({
      request: {
        headers: requestHeaders,
      },
    });
  }

  const isOldSessionPath = request.nextUrl.pathname.startsWith("/session");

  if (isOldSessionPath) {
    if (request.nextUrl.pathname === "/session") {
      // Redirect /session to /chat with query params preserved
      const url = new URL("/chat", request.url);
      for (const [key, value] of request.nextUrl.searchParams.entries()) {
        url.searchParams.append(key, value);
      }
      return NextResponse.redirect(url);
    }

    const secondPart = request.nextUrl.pathname.split("/")[2];

    const newPath = `/chat/${secondPart}`;

    return NextResponse.redirect(new URL(newPath, request.url));
  }
}

export const config = {
  matcher: ["/", "/session/:path*", "/chat/:path*"],
};
