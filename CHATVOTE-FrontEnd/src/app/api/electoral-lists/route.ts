import { type NextRequest, NextResponse } from "next/server";

import { type ElectoralListsByCommune } from "@lib/election/election.types";
import { db } from "@lib/firebase/firebase-admin";

export async function GET(request: NextRequest) {
  const communeCode = request.nextUrl.searchParams.get("commune_code");

  if (!communeCode) {
    return NextResponse.json(
      { error: "commune_code query parameter is required" },
      { status: 400 },
    );
  }

  try {
    // Fetch electoral lists and election config in parallel
    const [electoralDoc, configDoc] = await Promise.all([
      db.collection("electoral_lists").doc(communeCode).get(),
      db.collection("system_status").doc("election_config").get(),
    ]);

    if (!electoralDoc.exists) {
      return NextResponse.json(
        { error: "No electoral lists found for this commune" },
        { status: 404 },
      );
    }

    const data = electoralDoc.data() as ElectoralListsByCommune;
    const isSecondRoundActive =
      configDoc.exists &&
      configDoc.data()?.is_second_round_active === true;

    // When second round is active, serve lists_round_2 as lists
    let responseData: ElectoralListsByCommune & {
      is_second_round_active?: boolean;
      second_round_party_ids?: string[];
      lists_round_1?: ElectoralListsByCommune["lists"];
      list_count_round_1?: number;
    } = data;

    if (isSecondRoundActive && data.lists_round_2?.length) {
      responseData = {
        ...data,
        lists: data.lists_round_2,
        list_count: data.list_count_round_2 ?? data.lists_round_2.length,
        // Preserve first-round lists so the sidebar can offer a toggle
        lists_round_1: data.lists,
        list_count_round_1: data.list_count ?? data.lists.length,
        is_second_round_active: true,
      };

      // Fetch party_ids of second-round candidates for this commune
      const candidatesSnap = await db
        .collection("candidates")
        .where("municipality_code", "==", communeCode)
        .where("is_second_round", "==", true)
        .get();

      const partyIdSet = new Set<string>();
      for (const doc of candidatesSnap.docs) {
        const pids = doc.data().party_ids as string[] | undefined;
        pids?.forEach((id) => partyIdSet.add(id));
      }
      responseData.second_round_party_ids = [...partyIdSet];
    }

    const isDev = process.env.NEXT_PUBLIC_USE_FIREBASE_EMULATORS === "true";
    // Short browser cache (max-age) so users see fresh data quickly,
    // longer CDN cache (s-maxage) to absorb most Firestore reads.
    const browserMaxAge = isSecondRoundActive ? 60 : 300;
    const cdnMaxAge = isSecondRoundActive ? 300 : 3600;

    return NextResponse.json(responseData, {
      headers: {
        "Cache-Control": isDev
          ? "no-store"
          : `public, max-age=${browserMaxAge}, s-maxage=${cdnMaxAge}, stale-while-revalidate=${cdnMaxAge * 2}`,
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
