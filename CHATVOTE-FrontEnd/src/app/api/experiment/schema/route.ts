import { NextResponse } from "next/server";

const BACKEND_URL = process.env.NEXT_PUBLIC_SOCKET_URL || "http://localhost:8080";

export async function GET() {
  const res = await fetch(`${BACKEND_URL}/api/v1/experiment/metadata-schema`, {
    cache: "no-store",
  });

  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
