import { NextResponse } from "next/server";

import { getParties } from "@lib/firebase/firebase-server";

export async function GET() {
  const parties = await getParties();
  return NextResponse.json(parties);
}
