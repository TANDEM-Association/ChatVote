import Link from "next/link";

import { ArrowLeft, BarChart3Icon } from "lucide-react";

import { db } from "@lib/firebase/firebase-admin";
import { type PartyDetails } from "@lib/party-details";

import {
  type CoverageResponse,
  type CoverageSummary,
  type CommuneCoverage,
  type PartyCoverage,
  type CandidateCoverage,
} from "../../api/coverage/route";
import IconSidebar from "@components/layout/icon-sidebar";

import CoverageTablesClient from "./coverage-tables-client";

export const metadata = {
  title: "ChatVote - Coverage Report",
};

type TopicStatsResponse = {
  total_chunks: number;
  classified_chunks: number;
  themes: Array<{ by_party: Record<string, number> }>;
  collections: Record<string, { total: number; classified: number }>;
};

async function fetchTopicStats(): Promise<TopicStatsResponse | null> {
  const backendUrl =
    process.env.NEXT_PUBLIC_API_URL ||
    process.env.NEXT_PUBLIC_SOCKET_URL ||
    "http://localhost:8080";
  try {
    const res = await fetch(`${backendUrl}/api/v1/experiment/topic-stats`, {
      cache: "no-store",
    });
    if (!res.ok) return null;
    return res.json() as Promise<TopicStatsResponse>;
  } catch {
    return null;
  }
}

async function fetchCoverage(): Promise<CoverageResponse | null> {
  try {
    const [partiesSnap, municipalitiesSnap, sessionsSnap, topicStats] =
      await Promise.all([
        db.collection("parties").get(),
        db.collection("municipalities").get(),
        db.collection("chat_sessions").get(),
        fetchTopicStats(),
      ]);

    const questionsByCommune: Record<string, number> = {};
    for (const doc of sessionsSnap.docs) {
      const data = doc.data();
      const code: string | null =
        data.municipality_code ?? data.commune_code ?? null;
      if (code) {
        questionsByCommune[code] = (questionsByCommune[code] ?? 0) + 1;
      }
    }

    const partyChunkCounts: Record<string, number> = {};
    if (topicStats) {
      for (const theme of topicStats.themes) {
        for (const [party, count] of Object.entries(theme.by_party)) {
          partyChunkCounts[party] = (partyChunkCounts[party] ?? 0) + count;
        }
      }
    }

    const parties: PartyCoverage[] = partiesSnap.docs.map((doc) => {
      const data = doc.data() as PartyDetails & { short_name?: string };
      const partyId = data.party_id ?? doc.id;
      const name = data.name ?? "";
      const shortName = data.short_name ?? name;
      const chunkCount =
        partyChunkCounts[partyId] ??
        partyChunkCounts[shortName] ??
        partyChunkCounts[name] ??
        0;
      return {
        party_id: partyId,
        name: data.long_name ?? name,
        short_name: shortName,
        chunk_count: chunkCount,
        has_manifesto: Boolean(data.election_manifesto_url),
      };
    });
    parties.sort((a, b) => b.chunk_count - a.chunk_count);

    const communes: CommuneCoverage[] = municipalitiesSnap.docs.map((doc) => {
      const data = doc.data();
      const code: string = data.code ?? doc.id;
      return {
        code,
        name: data.name ?? code,
        list_count: data.list_count ?? 0,
        question_count: questionsByCommune[code] ?? 0,
        chunk_count: 0,
      };
    });
    communes.sort((a, b) => b.question_count - a.question_count);

    let candidates: CandidateCoverage[] = [];
    let totalCandidates = 0;
    try {
      const candidatesSnap = await db.collection("candidates").get();
      totalCandidates = candidatesSnap.size;
      candidates = candidatesSnap.docs.map((doc) => {
        const data = doc.data();
        return {
          candidate_id: doc.id,
          name:
            [data.first_name, data.last_name].filter(Boolean).join(" ") ||
            doc.id,
          commune_code: data.commune_code ?? data.municipality_code ?? "",
          commune_name: data.commune_name ?? data.municipality_name ?? "",
          has_website: Boolean(data.website_url || data.website),
          has_manifesto: Boolean(
            data.manifesto_url || data.election_manifesto_url,
          ),
          chunk_count: 0,
          party_label:
            data.list_label ?? data.nuance_label ?? data.party_name ?? "",
        };
      });
      candidates.sort((a, b) => a.name.localeCompare(b.name));
    } catch {
      // candidates collection may not exist
    }

    const summary: CoverageSummary = {
      total_communes: communes.length,
      total_parties: parties.length,
      total_questions: sessionsSnap.size,
      total_chunks: topicStats?.total_chunks ?? 0,
      total_candidates: totalCandidates,
    };

    return { communes, parties, candidates, summary };
  } catch (error) {
    console.error("[coverage] Error fetching coverage data:", error);
    return null;
  }
}

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

  const { summary, communes, parties, candidates } = data;

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
            <StatCard value={summary.total_questions} label="Questions asked" accentColor="#818CF8" />
            <StatCard value={summary.total_chunks} label="Indexed chunks" accentColor="#6D28D9" />
          </div>

          {/* Tables */}
          <CoverageTablesClient communes={communes} parties={parties} candidates={candidates} />
        </div>
      </div>
    </div>
  );
}
