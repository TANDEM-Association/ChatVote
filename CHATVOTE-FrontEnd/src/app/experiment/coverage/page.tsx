import Link from "next/link";

import { ArrowLeft, BarChart3Icon } from "lucide-react";

import IconSidebar from "@components/layout/icon-sidebar";

import { fetchCoverage } from "./coverage-data";
import CoverageTablesClient from "./coverage-tables-client";

export const metadata = {
  title: "ChatVote - Coverage Report",
};

// Cache coverage data for 10 minutes to avoid Firestore quota exhaustion
export const revalidate = 600;

function StatCard({
  value,
  label,
  accentColor,
}: {
  value: number | string;
  label: string;
  accentColor: string;
}) {
  return (
    <div className="bg-surface border border-border-subtle rounded-xl flex-1 min-w-0 overflow-hidden">
      <div className="h-[3px] w-full" style={{ backgroundColor: accentColor }} />
      <div className="p-4 pt-3">
        <p className="text-3xl font-extrabold text-foreground leading-none tabular-nums">
          {typeof value === "number" ? value.toLocaleString() : value}
        </p>
        <p className="mt-1 text-xs uppercase text-muted-foreground tracking-wider">
          {label}
        </p>
      </div>
    </div>
  );
}

export default async function CoveragePage() {
  const data = await fetchCoverage();

  if (!data) {
    return (
      <div className="flex h-screen bg-background">
        <IconSidebar />
        <div className="flex-1 overflow-y-auto flex items-center justify-center">
          <div className="flex flex-col items-center gap-4 text-muted-foreground">
            <p className="text-destructive font-semibold">
              Failed to load coverage data.
            </p>
            <p className="text-sm">
              Make sure the backend is running and Firestore is reachable.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const { summary, communes, parties, candidates, charts } = data;

  return (
    <div className="flex h-screen bg-background text-foreground">
      <IconSidebar />
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 py-6 space-y-8">
          {/* Header with back arrow */}
          <div className="flex items-center gap-4">
            <Link
              href="/experiment"
              className="flex items-center justify-center size-10 rounded-full border border-border-subtle bg-surface hover:bg-border-subtle/30 transition-colors shrink-0"
            >
              <ArrowLeft className="size-5 text-muted-foreground" />
            </Link>
            <div className="flex items-center gap-3">
              <BarChart3Icon className="text-muted-foreground size-6" />
              <div>
                <h1 className="text-2xl font-bold">Coverage Report</h1>
                <p className="text-muted-foreground text-sm">
                  Knowledge base coverage across communes, parties, candidates, and questions.
                </p>
              </div>
            </div>
          </div>

          {/* Summary stats */}
          <div className="flex gap-3 flex-wrap sm:flex-nowrap">
            <StatCard value={summary.total_communes} label="Communes" accentColor="#7C3AED" />
            <StatCard value={summary.total_parties} label="Parties" accentColor="#A78BFA" />
            <StatCard value={summary.total_candidates} label="Candidates" accentColor="#94A3B8" />
            <StatCard value={summary.total_lists} label="Electoral Lists" accentColor="#F59E0B" />
            <StatCard value={summary.total_questions} label="Questions asked" accentColor="#818CF8" />
            <StatCard value={summary.total_chunks} label="Indexed chunks" accentColor="#6D28D9" />
            <StatCard value={summary.scraped_candidates} label="With website" accentColor="#22c55e" />
            <StatCard value={summary.indexed_candidates} label="Indexed in RAG" accentColor="#6D28D9" />
          </div>

          {/* Tables */}
          <CoverageTablesClient communes={communes} parties={parties} candidates={candidates} coverageByCommune={charts?.coverageByCommune ?? {}} />
        </div>
      </div>
    </div>
  );
}
