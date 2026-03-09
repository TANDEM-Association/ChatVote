import { NextResponse } from "next/server";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_SOCKET_URL ||
  "http://localhost:8080";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ communeCode: string }> },
) {
  const { communeCode } = await params;

  try {
    const res = await fetch(
      `${BACKEND_URL}/api/v1/commune/${communeCode}/dashboard`,
      { cache: "no-store", signal: AbortSignal.timeout(7_000) },
    );

    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { error: "Dashboard request timed out or failed" },
      { status: 504 },
    );
  }
}
