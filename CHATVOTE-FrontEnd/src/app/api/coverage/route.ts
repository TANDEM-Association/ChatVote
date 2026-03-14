import { NextResponse } from "next/server";

import {
  type CandidateCoverage,
  type ChartAggregations,
  type CommuneCoverage,
  type CoverageResponse,
  type CoverageSummary,
  fetchCoverage,
  type PartyCoverage,
} from "../../admin/dashboard/[secret]/components/coverage-data";

// Re-export types so existing consumers that import from this route module still work
export type {
  CandidateCoverage,
  ChartAggregations,
  CommuneCoverage,
  CoverageResponse,
  CoverageSummary,
  PartyCoverage,
};

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
