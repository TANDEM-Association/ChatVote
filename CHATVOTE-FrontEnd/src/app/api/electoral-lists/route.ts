import { type NextRequest, NextResponse } from "next/server";

import { db } from "@lib/firebase/firebase-admin";
import { type ElectoralListsByCommune } from "@lib/election/election.types";

export async function GET(request: NextRequest) {
  const communeCode = request.nextUrl.searchParams.get("commune_code");

  if (!communeCode) {
    return NextResponse.json(
      { error: "commune_code query parameter is required" },
      { status: 400 },
    );
  }

  try {
    const doc = await db
      .collection("electoral_lists")
      .doc(communeCode)
      .get();

    if (!doc.exists) {
      return NextResponse.json(
        { error: "No electoral lists found for this commune" },
        { status: 404 },
      );
    }

    const data = doc.data() as ElectoralListsByCommune;

    const isDev =
      process.env.NEXT_PUBLIC_USE_FIREBASE_EMULATORS === "true";

    return NextResponse.json(data, {
      headers: {
        "Cache-Control": isDev
          ? "no-store"
          : "public, max-age=86400, s-maxage=86400, stale-while-revalidate=604800",
      },
    });
  } catch (error) {
    console.error("Error fetching electoral lists:", error);
    return NextResponse.json(
      { error: "Failed to fetch electoral lists" },
      { status: 500 },
    );
  }
}
