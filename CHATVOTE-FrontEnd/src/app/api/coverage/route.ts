import { NextResponse } from "next/server";

import {
  fetchCoverage,
  type CommuneCoverage,
  type PartyCoverage,
  type CandidateCoverage,
  type CoverageSummary,
  type CoverageResponse,
  type ChartAggregations,
} from "../../experiment/coverage/coverage-data";

// Re-export types so existing consumers that import from this route module still work
export type { CommuneCoverage, PartyCoverage, CandidateCoverage, CoverageSummary, CoverageResponse, ChartAggregations };

// Always fetch fresh data — admin dashboard needs real-time accuracy
export const dynamic = "force-dynamic";

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
