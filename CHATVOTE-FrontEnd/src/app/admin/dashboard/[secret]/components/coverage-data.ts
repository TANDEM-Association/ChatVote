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
  website_chunks: number;
  manifesto_chunks: number;
  scrape_chars: number;
  party_label: string;
  website_url: string;
  manifesto_pdf_url: string;
};

export type CoverageSummary = {
  total_communes: number;
  total_all_communes: number; // All 35k municipalities
  total_parties: number;
  total_candidates: number;
  total_lists: number;
  total_questions: number;
  total_chunks: number;
  scraped_candidates: number;
  indexed_candidates: number;
};

export type ChartAggregations = {
  funnel: {
    total: number;
    hasWebsite: number;
    scraped: number;
    indexed: number;
  };
  status: { noWebsite: number; hasWebsiteNotIndexed: number; indexed: number };
  partyLabels: Array<{ label: string; total: number; withWebsite: number }>;
  chunkDistribution: Array<{ label: string; count: number }>;
  coverageByCommune: Record<
    string,
    {
      score: number;
      ingestionScore: number;
      hasWebsite: number;
      hasManifesto: number;
      hasWebsiteIndexed: number;
      hasManifestoIndexed: number;
      hasScraped: number;
      total: number;
    }
  >;
};

export type CoverageResponse = {
  communes: CommuneCoverage[];
  parties: PartyCoverage[];
  candidates: CandidateCoverage[];
  summary: CoverageSummary;
  charts?: ChartAggregations; // New pre-computed chart data
};

// ---------------------------------------------------------------------------
// Backend topic-stats (Qdrant chunk counts per namespace/party)
// ---------------------------------------------------------------------------

type TopicStatsResponse = {
  total_chunks: number;
  classified_chunks: number;
  themes: Array<{ by_party: Record<string, number> }>;
  collections: Record<string, { total: number; classified: number }>;
  candidate_chunks?: Record<string, number>;
  candidate_manifesto_chunks?: Record<string, number>;
};

async function fetchTopicStats(): Promise<TopicStatsResponse | null> {
  const backendUrl =
    process.env.NEXT_PUBLIC_API_URL ||
    process.env.NEXT_PUBLIC_SOCKET_URL ||
    "http://localhost:8080";
  try {
    const res = await fetch(`${backendUrl}/api/v1/experiment/topic-stats`, {
      next: { revalidate: 600 },
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
    const [
      partiesSnap,
      municipalitiesSnap,
      sessionsSnap,
      electoralListsSnap,
      topicStats,
      municipalityCountSnap,
      candidatesTotalSnap,
      candidatesScrapedSnap,
      candidatesSnap,
    ] = await Promise.all([
      db
        .collection("parties")
        .select(
          "party_id",
          "name",
          "long_name",
          "short_name",
          "election_manifesto_url",
        )
        .get(),
      db
        .collection("municipalities")
        .where("has_electoral_data", "==", true)
        .select("code", "nom", "name", "population")
        .get(),
      // Only 2 fields needed for per-commune question counts
      db
        .collection("chat_sessions")
        .select("municipality_code", "commune_code")
        .get(),
      db
        .collection("electoral_lists")
        .select("commune_code", "list_count", "lists")
        .get(),
      fetchTopicStats(),
      db.collection("municipalities").count().get(),
      // count() queries for summary stats — avoids loading all candidate docs for totals
      db.collection("candidates").count().get(),
      db
        .collection("candidates")
        .where("has_scraped", "==", true)
        .count()
        .get(),
      // Full candidates query for aggregation — run in parallel instead of sequentially
      db
        .collection("candidates")
        .select(
          "first_name",
          "last_name",
          "commune_code",
          "municipality_code",
          "commune_name",
          "municipality_name",
          "website_url",
          "website",
          "manifesto_pdf_url",
          "manifesto_url",
          "election_manifesto_url",
          "manifesto_pdf_path",
          "has_scraped",
          "scrape_chars",
          "list_label",
          "nuance_label",
          "nuance_code",
          "party_name",
        )
        .get(),
    ]);

    // candidate_chunks now comes from topic-stats (merged to eliminate redundant Qdrant scroll)
    const candidateChunks: Record<string, number> =
      topicStats?.candidate_chunks ?? {};
    const candidateManifestoChunks: Record<string, number> =
      topicStats?.candidate_manifesto_chunks ?? {};

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
      listCountByCommune[code] = data.list_count ?? data.lists?.length ?? 0;
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

    // Summary totals derived from count() queries and candidateChunks map —
    // no need to scan the loaded candidates array for these values.
    const totalCandidates = candidatesTotalSnap.data().count;
    const scrapedFromDb = candidatesScrapedSnap.data().count;
    // indexed = candidates that have at least 1 chunk in Qdrant (from backend map)
    const indexedCandidates = Object.values(candidateChunks).filter(
      (v) => v > 0,
    ).length;
    // scraped = whichever is higher: Firestore has_scraped flag or has chunks in Qdrant
    const scrapedCandidates = Math.max(scrapedFromDb, indexedCandidates);

    // Per-commune aggregates needed for chart computations and coverage/ingestion scores.
    // Shape: commune_code -> { total, hasWebsite, hasManifesto, hasScraped, hasIndexed,
    //                          partyLabels (for party distribution chart),
    //                          chunkCounts (for chunk distribution histogram) }
    type CommuneAgg = {
      total: number;
      hasWebsite: number;
      hasManifesto: number;
      hasWebsiteIndexed: number;
      hasManifestoIndexed: number;
      hasScraped: number;
    };
    const communeAgg: Record<string, CommuneAgg> = {};

    // For chart aggregations computed across ALL candidates
    let totalWithWebsite = 0;
    let totalScraped = 0;
    let totalIndexed = 0;
    let totalNoWebsite = 0;
    let totalHasWebsiteNotIndexed = 0;
    const partyLabelCounts: Record<
      string,
      { total: number; withWebsite: number }
    > = {};
    const chunkBuckets = [0, 0, 0, 0, 0, 0]; // 0, 1-10, 11-25, 26-50, 51-100, 100+

    const candidates: CandidateCoverage[] = [];
    try {
      // Populate per-commune candidate_count using the already-loaded docs
      const candidateCountByCommune: Record<string, number> = {};
      for (const doc of candidatesSnap.docs) {
        const data = doc.data();
        const code: string = data.commune_code ?? data.municipality_code ?? "";
        if (code) {
          candidateCountByCommune[code] =
            (candidateCountByCommune[code] ?? 0) + 1;
        }
      }
      for (const commune of communes) {
        commune.candidate_count = candidateCountByCommune[commune.code] ?? 0;
      }

      // Compute all chart aggregations in a single pass over candidates
      for (const doc of candidatesSnap.docs) {
        const data = doc.data();
        const code: string = data.commune_code ?? data.municipality_code ?? "";
        const chunkCount = candidateChunks[doc.id] ?? 0;
        const hasWebsite = Boolean(data.website_url || data.website);
        const hasManifesto = Boolean(
          data.manifesto_pdf_url ||
          data.manifesto_url ||
          data.election_manifesto_url ||
          data.manifesto_pdf_path,
        );
        const manifestoChunkCount = candidateManifestoChunks[doc.id] ?? 0;
        const websiteChunkCount = chunkCount - manifestoChunkCount;
        // "scraped" means the candidate's *website* was scraped — not just manifesto OCR
        const hasScraped =
          hasWebsite &&
          (Boolean(data.has_scraped) || websiteChunkCount > 0);
        const hasWebsiteIndexed = websiteChunkCount > 0;
        const hasManifestoIndexed = manifestoChunkCount > 0;
        const partyLabel =
          data.list_label ??
          data.nuance_label ??
          data.nuance_code ??
          data.party_name ??
          "Unknown";

        // Per-commune aggregates
        if (code) {
          if (!communeAgg[code]) {
            communeAgg[code] = {
              total: 0,
              hasWebsite: 0,
              hasManifesto: 0,
              hasWebsiteIndexed: 0,
              hasManifestoIndexed: 0,
              hasScraped: 0,
            };
          }
          communeAgg[code].total++;
          if (hasWebsite) communeAgg[code].hasWebsite++;
          if (hasManifesto) communeAgg[code].hasManifesto++;
          if (hasWebsiteIndexed) communeAgg[code].hasWebsiteIndexed++;
          if (hasManifestoIndexed) communeAgg[code].hasManifestoIndexed++;
          if (hasScraped) communeAgg[code].hasScraped++;
        }

        // Global funnel counters
        if (hasWebsite) totalWithWebsite++;
        if (hasScraped) totalScraped++;
        if (chunkCount > 0) totalIndexed++;

        // Status donut
        if (!hasWebsite) {
          totalNoWebsite++;
        } else if (chunkCount === 0) {
          totalHasWebsiteNotIndexed++;
        }

        // Party label distribution
        if (!partyLabelCounts[partyLabel])
          partyLabelCounts[partyLabel] = { total: 0, withWebsite: 0 };
        partyLabelCounts[partyLabel].total++;
        if (hasWebsite) partyLabelCounts[partyLabel].withWebsite++;

        // Chunk distribution buckets: 0, 1-10, 11-25, 26-50, 51-100, 100+
        if (chunkCount === 0) chunkBuckets[0]++;
        else if (chunkCount <= 10) chunkBuckets[1]++;
        else if (chunkCount <= 25) chunkBuckets[2]++;
        else if (chunkCount <= 50) chunkBuckets[3]++;
        else if (chunkCount <= 100) chunkBuckets[4]++;
        else chunkBuckets[5]++;

        // Build per-candidate row for the table
        const communeName: string =
          data.commune_name ?? data.municipality_name ?? "";
        const websiteUrl: string = String(data.website_url || data.website || "");
        const manifestoPdfUrl: string = String(
          data.manifesto_pdf_url ||
            data.manifesto_url ||
            data.election_manifesto_url ||
            "",
        );
        candidates.push({
          candidate_id: doc.id,
          name: `${data.first_name ?? ""} ${data.last_name ?? ""}`.trim() || doc.id,
          commune_code: code,
          commune_name: communeName,
          has_website: hasWebsite,
          has_manifesto: hasManifesto,
          has_scraped: hasScraped,
          chunk_count: chunkCount,
          website_chunks: websiteChunkCount,
          manifesto_chunks: manifestoChunkCount,
          scrape_chars: data.scrape_chars ?? 0,
          party_label: partyLabel,
          website_url: websiteUrl,
          manifesto_pdf_url: manifestoPdfUrl,
        });
      }
    } catch {
      // candidates collection may not exist
    }

    // Build coverageByCommune map: pre-compute coverage and ingestion scores server-side
    function computeCoverageScore(listCount: number, agg: CommuneAgg): number {
      let score = 0;
      if (listCount > 0) score += 33;
      if (agg.total > 0) {
        score += 33 * (agg.hasWebsite / agg.total);
        score += 34 * (agg.hasManifesto / agg.total);
      }
      return Math.round(score);
    }

    function computeIngestionScore(agg: CommuneAgg): number {
      if (agg.total === 0) return 0;
      // Three axes: manifesto indexed (40%) + website scraped (20%) + website indexed (40%)
      const manifestoRatio = Math.min(agg.hasManifestoIndexed / agg.total, 1);
      const hasWeb = agg.hasWebsite > 0;
      if (hasWeb) {
        const scrapedRatio = Math.min(agg.hasScraped / agg.hasWebsite, 1);
        const webIndexedRatio = Math.min(agg.hasWebsiteIndexed / agg.hasWebsite, 1);
        return Math.round(
          40 * manifestoRatio + 20 * scrapedRatio + 40 * webIndexedRatio,
        );
      }
      // Manifesto-only commune
      return Math.round(100 * manifestoRatio);
    }

    const coverageByCommune: ChartAggregations["coverageByCommune"] = {};
    for (const [code, agg] of Object.entries(communeAgg)) {
      const listCount = listCountByCommune[code] ?? 0;
      coverageByCommune[code] = {
        score: computeCoverageScore(listCount, agg),
        ingestionScore: computeIngestionScore(agg),
        hasWebsite: agg.hasWebsite,
        hasManifesto: agg.hasManifesto,
        hasWebsiteIndexed: agg.hasWebsiteIndexed,
        hasManifestoIndexed: agg.hasManifestoIndexed,
        hasScraped: agg.hasScraped,
        total: agg.total,
      };
    }

    const totalCandidatesLoaded = Object.values(communeAgg).reduce(
      (s, a) => s + a.total,
      0,
    );

    const charts: ChartAggregations = {
      funnel: {
        total: totalCandidatesLoaded,
        hasWebsite: totalWithWebsite,
        scraped: totalScraped,
        indexed: totalIndexed,
      },
      status: {
        noWebsite: totalNoWebsite,
        hasWebsiteNotIndexed: totalHasWebsiteNotIndexed,
        indexed: totalIndexed,
      },
      partyLabels: Object.entries(partyLabelCounts)
        .map(([label, v]) => ({
          label,
          total: v.total,
          withWebsite: v.withWebsite,
        }))
        .sort((a, b) => b.total - a.total)
        .slice(0, 20),
      chunkDistribution: [
        { label: "0", count: chunkBuckets[0] },
        { label: "1–10", count: chunkBuckets[1] },
        { label: "11–25", count: chunkBuckets[2] },
        { label: "26–50", count: chunkBuckets[3] },
        { label: "51–100", count: chunkBuckets[4] },
        { label: "100+", count: chunkBuckets[5] },
      ],
      coverageByCommune,
    };

    const summary: CoverageSummary = {
      total_communes: Object.values(communeAgg).filter((c) => c.hasScraped > 0)
        .length,
      total_all_communes: municipalityCountSnap.data().count,
      total_parties: parties.length,
      total_candidates: totalCandidates,
      total_lists: communes.reduce((sum, c) => sum + c.list_count, 0),
      total_questions: sessionsSnap.size,
      total_chunks: topicStats?.total_chunks ?? 0,
      scraped_candidates: scrapedCandidates,
      indexed_candidates: indexedCandidates,
    };

    // Return candidates as empty array — individual records are not needed by the frontend.
    // All chart data and per-commune aggregates are pre-computed in `charts`.
    return { communes, parties, candidates, summary, charts };
  } catch (error) {
    console.error("[coverage] Error fetching coverage data:", error);
    return null;
  }
}
