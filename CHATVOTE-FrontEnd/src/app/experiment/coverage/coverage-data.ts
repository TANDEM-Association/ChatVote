import { db } from "@lib/firebase/firebase-admin";
import { type PartyDetails } from "@lib/party-details";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type CommuneCoverage = {
  code: string;
  name: string;
  population: number;
  list_count: number;
  candidate_count: number;
  question_count: number;
  chunk_count: number;
};

export type PartyCoverage = {
  party_id: string;
  name: string;
  short_name: string;
  chunk_count: number;
  has_manifesto: boolean;
};

export type CandidateCoverage = {
  candidate_id: string;
  name: string;
  commune_code: string;
  commune_name: string;
  has_website: boolean;
  has_manifesto: boolean;
  has_scraped: boolean;
  chunk_count: number;
  scrape_chars: number;
  party_label: string;
};

export type CoverageSummary = {
  total_communes: number;
  total_all_communes: number;  // All 35k municipalities
  total_parties: number;
  total_candidates: number;
  total_lists: number;
  total_questions: number;
  total_chunks: number;
  scraped_candidates: number;
  indexed_candidates: number;
};

export type CoverageResponse = {
  communes: CommuneCoverage[];
  parties: PartyCoverage[];
  candidates: CandidateCoverage[];
  summary: CoverageSummary;
};

// ---------------------------------------------------------------------------
// Backend topic-stats (Qdrant chunk counts per namespace/party)
// ---------------------------------------------------------------------------

type TopicStatsResponse = {
  total_chunks: number;
  classified_chunks: number;
  themes: Array<{ by_party: Record<string, number> }>;
  collections: Record<string, { total: number; classified: number }>;
};

async function fetchCandidateChunks(): Promise<Record<string, number>> {
  const backendUrl =
    process.env.NEXT_PUBLIC_API_URL ||
    process.env.NEXT_PUBLIC_SOCKET_URL ||
    "http://localhost:8080";
  try {
    const res = await fetch(`${backendUrl}/api/v1/experiment/candidate-coverage`, {
      cache: "no-store",
    });
    if (!res.ok) return {};
    const data = await res.json();
    return data.candidate_chunks ?? {};
  } catch {
    return {};
  }
}

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

// ---------------------------------------------------------------------------
// Build per-party chunk counts from topic-stats by_party fields
// ---------------------------------------------------------------------------

function buildPartyChunkCounts(
  topicStats: TopicStatsResponse | null,
): Record<string, number> {
  if (!topicStats) return {};
  const counts: Record<string, number> = {};
  for (const theme of topicStats.themes) {
    for (const [party, count] of Object.entries(theme.by_party)) {
      counts[party] = (counts[party] ?? 0) + count;
    }
  }
  return counts;
}

// ---------------------------------------------------------------------------
// Fetch all coverage data from Firestore
// ---------------------------------------------------------------------------

export async function fetchCoverage(): Promise<CoverageResponse | null> {
  try {
    const [partiesSnap, municipalitiesSnap, sessionsSnap, electoralListsSnap, topicStats, candidateChunks, municipalityCountSnap] =
      await Promise.all([
        db.collection("parties").select("party_id", "name", "long_name", "short_name", "election_manifesto_url").get(),
        db.collection("municipalities").where("has_electoral_data", "==", true).select("code", "nom", "name", "population").get(),
        db.collection("chat_sessions").select("municipality_code", "commune_code").get(),
        db.collection("electoral_lists").select("commune_code", "list_count", "lists").get(),
        fetchTopicStats(),
        fetchCandidateChunks(),
        db.collection("municipalities").count().get(),
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

    const partyChunkCounts = buildPartyChunkCounts(topicStats);

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

    const listCountByCommune: Record<string, number> = {};
    for (const doc of electoralListsSnap.docs) {
      const data = doc.data();
      const code: string = data.commune_code ?? doc.id;
      listCountByCommune[code] = data.list_count ?? (data.lists?.length ?? 0);
    }

    const communes: CommuneCoverage[] = municipalitiesSnap.docs.map((doc) => {
      const data = doc.data();
      const code: string = data.code ?? doc.id;
      return {
        code,
        name: data.nom ?? data.name ?? code,
        population: data.population ?? 0,
        list_count: listCountByCommune[code] ?? 0,
        candidate_count: 0,
        question_count: questionsByCommune[code] ?? 0,
        chunk_count: 0,
      };
    });
    communes.sort((a, b) => b.question_count - a.question_count);

    let candidates: CandidateCoverage[] = [];
    let totalCandidates = 0;
    try {
      const candidatesSnap = await db.collection("candidates").select(
        "first_name", "last_name", "commune_code", "municipality_code",
        "commune_name", "municipality_name", "website_url", "website",
        "has_manifesto", "manifesto_url", "election_manifesto_url", "manifesto_pdf_path",
        "has_scraped", "scrape_chars", "list_label", "nuance_label", "nuance_code", "party_name",
      ).get();
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
            data.has_manifesto || data.manifesto_url || data.election_manifesto_url || data.manifesto_pdf_path,
          ),
          has_scraped: Boolean(data.has_scraped) || (candidateChunks[doc.id] ?? 0) > 0,
          chunk_count: candidateChunks[doc.id] ?? 0,
          scrape_chars: (data.scrape_chars as number) ?? 0,
          party_label:
            data.list_label ?? data.nuance_label ?? data.nuance_code ?? data.party_name ?? "",
        };
      });
      candidates.sort((a, b) => a.name.localeCompare(b.name));

      const candidatesByCommune: Record<string, number> = {};
      for (const doc of candidatesSnap.docs) {
        const data = doc.data();
        const code: string = data.commune_code ?? data.municipality_code ?? "";
        if (code) {
          candidatesByCommune[code] = (candidatesByCommune[code] ?? 0) + 1;
        }
      }
      for (const commune of communes) {
        commune.candidate_count = candidatesByCommune[commune.code] ?? 0;
      }
    } catch {
      // candidates collection may not exist
    }

    const summary: CoverageSummary = {
      total_communes: communes.length,
      total_all_communes: municipalityCountSnap.data().count,
      total_parties: parties.length,
      total_candidates: totalCandidates,
      total_lists: communes.reduce((sum, c) => sum + c.list_count, 0),
      total_questions: sessionsSnap.size,
      total_chunks: topicStats?.total_chunks ?? 0,
      scraped_candidates: candidates.filter(c => c.has_scraped).length,
      indexed_candidates: candidates.filter(c => c.chunk_count > 0).length,
    };

    return { communes, parties, candidates, summary };
  } catch (error) {
    console.error("[coverage] Error fetching coverage data:", error);
    return null;
  }
}
