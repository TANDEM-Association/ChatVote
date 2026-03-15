import { type NextRequest, NextResponse } from "next/server";

import {
  type ElectoralList,
  type ElectoralListsByCommune,
} from "@lib/election/election.types";
import { db } from "@lib/firebase/firebase-admin";

export type CandidateListItem = ElectoralList & {
  candidate_id: string | null;
  party_ids: string[];
  website_url: string | null;
  manifesto_pdf_url: string | null;
};

export type CandidateListsResponse = {
  lists: CandidateListItem[];
  source: "electoral_lists" | "candidates";
};

export async function GET(request: NextRequest) {
  const municipalityCode = request.nextUrl.searchParams.get("municipalityCode");

  if (!municipalityCode) {
    return NextResponse.json(
      { error: "municipalityCode query parameter is required" },
      { status: 400 },
    );
  }

  const isDev = process.env.NEXT_PUBLIC_USE_FIREBASE_EMULATORS === "true";
  const cacheHeaders = {
    "Cache-Control": isDev
      ? "no-store"
      : "public, max-age=3600, s-maxage=3600, stale-while-revalidate=86400",
  };

  try {
    // Fetch candidates from Firestore
    const candidatesSnap = await db
      .collection("candidates")
      .where("municipality_code", "==", municipalityCode)
      .get();

    if (candidatesSnap.empty) {
      return NextResponse.json(
        { lists: [], source: "candidates" } satisfies CandidateListsResponse,
        { headers: cacheHeaders },
      );
    }

    // Build candidate map by last_name for enrichment
    const candidatesByName = new Map<
      string,
      {
        candidate_id: string;
        party_ids: string[];
        website_url: string | null;
        manifesto_pdf_url: string | null;
      }
    >();
    for (const doc of candidatesSnap.docs) {
      const d = doc.data();
      const key = (d.last_name as string)?.toUpperCase();
      if (key) {
        candidatesByName.set(key, {
          candidate_id: doc.id,
          party_ids: (d.party_ids as string[]) ?? [],
          website_url: (d.website_url as string) ?? null,
          manifesto_pdf_url: (d.manifesto_pdf_url as string) ?? null,
        });
      }
    }

    // Try electoral lists first for structured data
    const electoralDoc = await db
      .collection("electoral_lists")
      .doc(municipalityCode)
      .get();

    if (electoralDoc.exists) {
      const data = electoralDoc.data() as ElectoralListsByCommune;
      const enrichedLists: CandidateListItem[] = data.lists.map((list) => {
        const match = candidatesByName.get(list.head_last_name?.toUpperCase());
        return {
          ...list,
          candidate_id: match?.candidate_id ?? null,
          party_ids: match?.party_ids ?? [],
          website_url: match?.website_url ?? null,
          manifesto_pdf_url: match?.manifesto_pdf_url ?? null,
        };
      });

      return NextResponse.json(
        {
          lists: enrichedLists,
          source: "electoral_lists",
        } satisfies CandidateListsResponse,
        { headers: cacheHeaders },
      );
    }

    // Fallback: build list items directly from candidates
    const lists: CandidateListItem[] = candidatesSnap.docs.map((doc) => {
      const d = doc.data();
      return {
        panel_number: 0,
        list_label: (d.position as string) ?? "",
        list_short_label: "",
        nuance_code: null,
        nuance_label: null,
        head_first_name: (d.first_name as string) ?? "",
        head_last_name: (d.last_name as string) ?? "",
        candidate_id: doc.id,
        party_ids: (d.party_ids as string[]) ?? [],
        website_url: (d.website_url as string) ?? null,
        manifesto_pdf_url: (d.manifesto_pdf_url as string) ?? null,
      };
    });

    return NextResponse.json(
      { lists, source: "candidates" } satisfies CandidateListsResponse,
      { headers: cacheHeaders },
    );
  } catch (error) {
    console.error("[candidate-lists] Failed:", error);
    return NextResponse.json(
      { error: "Failed to fetch candidate lists" },
      { status: 500 },
    );
  }
}
