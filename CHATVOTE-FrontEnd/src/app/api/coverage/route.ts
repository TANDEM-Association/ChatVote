import { NextResponse } from "next/server";

import {
  fetchCoverage,
  type CommuneCoverage,
  type PartyCoverage,
  type CandidateCoverage,
  type CoverageSummary,
  type CoverageResponse,
} from "../../experiment/coverage/coverage-data";

// Re-export types so existing consumers that import from this route module still work
export type { CommuneCoverage, PartyCoverage, CandidateCoverage, CoverageSummary, CoverageResponse };

// Cache this route for 10 minutes to avoid Firestore quota exhaustion
export const revalidate = 600;

// ---------------------------------------------------------------------------
// GET handler
// ---------------------------------------------------------------------------

export async function GET() {
  try {
    const data = await fetchCoverage();

    if (!data) {
      return NextResponse.json(
        { error: "Failed to fetch coverage data" },
        { status: 500 },
      );
    }

    return NextResponse.json(data);
  } catch (error) {
    console.error("[coverage] Error fetching coverage data:", error);
    return NextResponse.json(
      { error: "Failed to fetch coverage data" },
      { status: 500 },
    );
  }
}
