import { google } from '@ai-sdk/google';
import { type UIMessage, type LanguageModel, convertToModelMessages, stepCountIs, streamText, tool } from 'ai';
import { z } from 'zod/v4';

import { deepResearch } from '@lib/ai/deep-research';
import { embedQuery } from '@lib/ai/embedding';
import { COLLECTIONS } from '@lib/ai/qdrant-client';
import {
  type SearchResult,
  searchQdrant,
  searchQdrantBroad,
  searchQdrantRaw,
  deduplicateResults,
} from '@lib/ai/qdrant-search';
import { scalewayChat } from '@lib/ai/providers';
import { db, auth } from '@lib/firebase/firebase-admin';

export const maxDuration = 120;
export const preferredRegion = 'cdg1';

// ── data.gouv.fr MCP client ──────────────────────────────────────────────────
// Uses the official data.gouv.fr MCP server (https://github.com/datagouv/datagouv-mcp)
// Public endpoint: mcp.data.gouv.fr — free, no API key required
interface DataGouvDataset {
  id: string;
  title: string;
  description: string;
  url: string;
  organization?: { name: string };
  frequency?: string;
  last_modified?: string;
  resources?: Array<{ title: string; format: string; url: string }>;
}

async function searchDataGouvMcp(query: string, limit = 5): Promise<DataGouvDataset[]> {
  // Call the MCP server's search_datasets tool via JSON-RPC over SSE/HTTP
  // The MCP endpoint exposes standard MCP protocol at mcp.data.gouv.fr/mcp
  // Fallback to direct REST API if MCP call fails
  try {
    const mcpUrl = 'https://mcp.data.gouv.fr/mcp';
    const res = await fetch(mcpUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 1,
        method: 'tools/call',
        params: {
          name: 'search_datasets',
          arguments: { query, page_size: limit },
        },
      }),
      signal: AbortSignal.timeout(10000),
    });
    if (res.ok) {
      const json = await res.json();
      const content = json?.result?.content;
      if (Array.isArray(content) && content.length > 0) {
        // MCP returns content as text blocks, parse the first one
        const text = content[0]?.text ?? '';
        try {
          const parsed = JSON.parse(text);
          const datasets = Array.isArray(parsed) ? parsed : parsed.data ?? [];
          return datasets.slice(0, limit).map((d: any) => ({
            id: d.id ?? '',
            title: d.title ?? '',
            description: (d.description ?? '').slice(0, 300),
            url: d.url ?? d.page ?? `https://www.data.gouv.fr/fr/datasets/${d.id}/`,
            organization: d.organization ? { name: d.organization.name ?? d.organization } : undefined,
            frequency: d.frequency,
            last_modified: d.last_modified,
            resources: (d.resources ?? []).slice(0, 3).map((r: any) => ({
              title: r.title ?? '',
              format: r.format ?? '',
              url: r.url ?? '',
            })),
          }));
        } catch {
          // MCP returned non-JSON text, wrap it as a single result
          return [{ id: '1', title: query, description: text.slice(0, 300), url: 'https://www.data.gouv.fr' }];
        }
      }
    }
  } catch (err) {
    console.warn('[ai-chat] MCP data.gouv.fr call failed, falling back to REST API:', err);
  }

  // Fallback: direct REST API
  const apiUrl = `https://www.data.gouv.fr/api/1/datasets/?q=${encodeURIComponent(query)}&page_size=${limit}`;
  const res = await fetch(apiUrl, { signal: AbortSignal.timeout(8000) });
  if (!res.ok) throw new Error(`data.gouv.fr API returned ${res.status}`);
  const json = await res.json();
  return (json.data ?? []).map((d: any) => ({
    id: d.id,
    title: d.title,
    description: (d.description ?? '').slice(0, 300),
    url: d.page ?? `https://www.data.gouv.fr/fr/datasets/${d.id}/`,
    organization: d.organization ? { name: d.organization.name } : undefined,
    frequency: d.frequency,
    last_modified: d.last_modified,
    resources: (d.resources ?? []).slice(0, 3).map((r: any) => ({
      title: r.title,
      format: r.format,
      url: r.url,
    })),
  }));
}


function buildTools(enabledFeatures: string[] | undefined, candidateIds: string[] = []) {
  const features = enabledFeatures ?? ['rag'];
  const ragEnabled = features.includes('rag');

  return {
    // ── RAG search tools (feature-gated) ────────────────────────────────────
    ...(ragEnabled
      ? {
          searchPartyManifesto: tool({
            description:
              "Search a political party's manifesto/programme for relevant content. Call this for EACH relevant party. You can search multiple parties simultaneously.",
            inputSchema: z.object({
              partyId: z.string().describe('The party identifier to search within'),
              query: z.string().describe('The search query to find relevant content'),
            }),
            execute: async (input) => {
              const { partyId, query } = input;
              const normalizedPartyId = partyId.toLowerCase();
              try {
                let results = await searchQdrant(
                  COLLECTIONS.allParties,
                  query,
                  'metadata.namespace',
                  normalizedPartyId,
                  8,
                );
                // Tier 1: retry with lower threshold + broad scope
                if (results.length < 3) {
                  console.log(`[qdrant:fallback] searchPartyManifesto: ${results.length} results at 0.35, retrying at 0.25 broad`);
                  const broadResults = await searchQdrantBroad(COLLECTIONS.allParties, query, 8);
                  results = deduplicateResults([...results, ...broadResults]);
                }
                // Tier 2: deep research sub-agent
                if (results.length < 3) {
                  console.log(`[deep-research] searchPartyManifesto: ${results.length} results after Tier 1, launching deep research`);
                  const research = await deepResearch({ originalQuery: query, collections: [COLLECTIONS.allParties] });
                  results = deduplicateResults([...results, ...research.findings]);
                  console.log(`[deep-research] Found ${research.findings.length} additional results via sub-agent`);
                }
                return { partyId, results, count: results.length };
              } catch (err) {
                console.error('[ai-chat] searchPartyManifesto error:', err);
                return { partyId, results: [] as SearchResult[], count: 0, error: String(err) };
              }
            },
          }),
          searchCandidateWebsite: tool({
            description: "Search a single candidate's website content. Prefer searchAllCandidates when searching the whole commune.",
            inputSchema: z.object({
              candidateId: z.string().describe('The candidate identifier to search within'),
              query: z.string().describe('The search query to find relevant content'),
            }),
            execute: async (input) => {
              const { candidateId, query } = input;
              const normalizedCandidateId = candidateId.toLowerCase();
              try {
                let results = await searchQdrant(
                  COLLECTIONS.candidatesWebsites,
                  query,
                  'metadata.namespace',
                  normalizedCandidateId,
                  5,
                );
                // Tier 1: retry with lower threshold + broad scope
                if (results.length < 3) {
                  console.log(`[qdrant:fallback] searchCandidateWebsite: ${results.length} results at 0.35, retrying at 0.25 broad`);
                  const broadResults = await searchQdrantBroad(COLLECTIONS.candidatesWebsites, query, 8);
                  results = deduplicateResults([...results, ...broadResults]);
                }
                // Tier 2: deep research sub-agent
                if (results.length < 3) {
                  console.log(`[deep-research] searchCandidateWebsite: ${results.length} results after Tier 1, launching deep research`);
                  const research = await deepResearch({ originalQuery: query, collections: [COLLECTIONS.candidatesWebsites], candidateIds: [candidateId] });
                  results = deduplicateResults([...results, ...research.findings]);
                  console.log(`[deep-research] Found ${research.findings.length} additional results via sub-agent`);
                }
                return { candidateId, results, count: results.length };
              } catch (err) {
                console.error('[ai-chat] searchCandidateWebsite error:', err);
                return { candidateId, results: [] as SearchResult[], count: 0, error: String(err) };
              }
            },
          }),
          // Search ALL candidates in the commune with multi-query support, each query re-ranked independently
          ...(candidateIds.length > 0
            ? {
                searchAllCandidates: tool({
                  description:
                    'Search ALL candidates in the current commune. Accepts multiple queries for broader coverage — each query is re-ranked independently then merged. Use this for any general question about the commune.',
                  inputSchema: z.object({
                    queries: z
                      .array(z.string())
                      .min(1)
                      .max(5)
                      .describe(
                        'Search queries — use 2-3 varied phrasings for better recall (e.g. ["transports en commun", "mobilité urbaine", "vélo piste cyclable"])',
                      ),
                  }),
                  execute: async (input) => {
                    const { queries } = input;
                    try {
                      // Pre-embed all unique queries once (avoids N×M redundant embedding calls)
                      const vectors = await Promise.all(queries.map((q) => embedQuery(q)));
                      const queryVectors = new Map(queries.map((q, i) => [q, vectors[i]]));

                      // For each query, search all candidates in parallel and re-rank independently
                      const perQueryResults = await Promise.all(
                        queries.map(async (query) => {
                          const vec = queryVectors.get(query)!;
                          const allResults = await Promise.all(
                            candidateIds.map(async (cid) => {
                              let results = await searchQdrant(
                                COLLECTIONS.candidatesWebsites,
                                query,
                                'metadata.namespace',
                                cid.toLowerCase(),
                                5,
                                vec,
                              );
                              // Tier 1: retry at lower threshold (keep namespace scoping)
                              if (results.length < 3) {
                                console.log(`[qdrant:fallback] searchAllCandidates/${cid}: ${results.length} results at 0.35, retrying at 0.25`);
                                const retryResults = await searchQdrant(
                                  COLLECTIONS.candidatesWebsites,
                                  query,
                                  'metadata.namespace',
                                  cid.toLowerCase(),
                                  5,
                                  vec,
                                  { scoreThreshold: 0.25 },
                                );
                                results = deduplicateResults([...results, ...retryResults]);
                              }
                              return results.map((r) => ({ ...r, candidateId: cid }));
                            }),
                          );
                          // Re-rank this query's results by score, take top 10 per query
                          return allResults
                            .flat()
                            .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
                            .slice(0, 10);
                        }),
                      );

                      // Merge all queries, deduplicate by content hash, keep highest score
                      const seen = new Map<string, (typeof perQueryResults)[0][0]>();
                      for (const results of perQueryResults) {
                        for (const r of results) {
                          const key = `${r.party_id}:${r.content.slice(0, 100)}`;
                          const existing = seen.get(key);
                          if (!existing || (r.score ?? 0) > (existing.score ?? 0)) {
                            seen.set(key, r);
                          }
                        }
                      }

                      const merged = Array.from(seen.values())
                        .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
                        .slice(0, 20)
                        .map((r, idx) => ({ ...r, id: idx + 1 }));

                      const candidatesWithResults = new Set(merged.map((r) => r.candidateId));

                      return {
                        results: merged,
                        count: merged.length,
                        queriesUsed: queries.length,
                        candidatesSearched: candidateIds.length,
                        candidatesWithResults: candidatesWithResults.size,
                      };
                    } catch (err) {
                      console.error('[ai-chat] searchAllCandidates error:', err);
                      return { results: [] as SearchResult[], count: 0, error: String(err) };
                    }
                  },
                }),
              }
            : {}),
        }
      : {}),

    // ── Voting records (Qdrant collection) ──────────────────────────────────
    ...(features.includes('voting-records')
      ? {
          searchVotingRecords: tool({
            description:
              'Search parliamentary voting records to find how parties voted on specific topics, bills, or laws.',
            inputSchema: z.object({
              query: z.string().describe('The topic or bill to search voting records for'),
            }),
            execute: async (input) => {
              try {
                let results = await searchQdrant(
                  COLLECTIONS.votingBehavior,
                  input.query,
                  'metadata.namespace',
                  'vote_summary',
                  8,
                );
                // Tier 1: retry with lower threshold + broad scope
                if (results.length < 3) {
                  console.log(`[qdrant:fallback] searchVotingRecords: ${results.length} results at 0.35, retrying at 0.25 broad`);
                  const broadResults = await searchQdrantBroad(COLLECTIONS.votingBehavior, input.query, 8);
                  results = deduplicateResults([...results, ...broadResults]);
                }
                // Tier 2: deep research sub-agent
                if (results.length < 3) {
                  console.log(`[deep-research] searchVotingRecords: ${results.length} results after Tier 1, launching deep research`);
                  const research = await deepResearch({ originalQuery: input.query, collections: [COLLECTIONS.votingBehavior] });
                  results = deduplicateResults([...results, ...research.findings]);
                  console.log(`[deep-research] Found ${research.findings.length} additional results via sub-agent`);
                }
                return { results, count: results.length };
              } catch (err) {
                console.error('[ai-chat] searchVotingRecords error:', err);
                return { results: [] as SearchResult[], count: 0, error: String(err) };
              }
            },
          }),
        }
      : {}),

    // ── Parliamentary questions (Qdrant collection) ──────────────────────────
    ...(features.includes('parliamentary')
      ? {
          searchParliamentaryQuestions: tool({
            description:
              'Search parliamentary questions asked by members of parliament on specific topics.',
            inputSchema: z.object({
              query: z.string().describe('The topic to search parliamentary questions for'),
              partyId: z
                .string()
                .optional()
                .describe('Optional party ID to filter questions by party'),
            }),
            execute: async (input) => {
              const namespace = input.partyId
                ? `${input.partyId}-parliamentary-questions`
                : undefined;
              try {
                let results: SearchResult[];
                if (namespace) {
                  results = await searchQdrant(
                    COLLECTIONS.parliamentaryQuestions,
                    input.query,
                    'metadata.namespace',
                    namespace,
                    8,
                    undefined,
                    { mustNot: null },
                  );
                } else {
                  results = await searchQdrantRaw(
                    COLLECTIONS.parliamentaryQuestions,
                    input.query,
                    8,
                  );
                }
                // Tier 1: retry with lower threshold + broad scope
                if (results.length < 3) {
                  console.log(`[qdrant:fallback] searchParliamentaryQuestions: ${results.length} results at 0.35, retrying at 0.25 broad`);
                  const broadResults = await searchQdrantBroad(
                    COLLECTIONS.parliamentaryQuestions,
                    input.query,
                    8,
                    undefined,
                    { mustNot: null },
                  );
                  results = deduplicateResults([...results, ...broadResults]);
                }
                // Tier 2: deep research sub-agent
                if (results.length < 3) {
                  console.log(`[deep-research] searchParliamentaryQuestions: ${results.length} results after Tier 1, launching deep research`);
                  const research = await deepResearch({ originalQuery: input.query, collections: [COLLECTIONS.parliamentaryQuestions] });
                  results = deduplicateResults([...results, ...research.findings]);
                  console.log(`[deep-research] Found ${research.findings.length} additional results via sub-agent`);
                }
                return { partyId: input.partyId, results, count: results.length };
              } catch (err) {
                console.error('[ai-chat] searchParliamentaryQuestions error:', err);
                return {
                  partyId: input.partyId,
                  results: [] as SearchResult[],
                  count: 0,
                  error: String(err),
                };
              }
            },
          }),
        }
      : {}),

    // ── data.gouv.fr open data search ────────────────────────────────────────
    ...(features.includes('data-gouv')
      ? {
          searchDataGouv: tool({
            description:
              'Search open government data on data.gouv.fr. Returns datasets with descriptions and download links. Use for statistics, public data, budgets, demographics, etc.',
            inputSchema: z.object({
              query: z.string().describe('The search query in French'),
            }),
            execute: async (input) => {
              try {
                const datasets = await searchDataGouvMcp(input.query, 5);
                return { datasets, count: datasets.length };
              } catch (err) {
                console.error('[ai-chat] searchDataGouv error:', err);
                return { datasets: [], count: 0, error: String(err) };
              }
            },
          }),
        }
      : {}),

    // ── Web search (Google Gemini grounding) ──────────────────────────────────
    ...(features.includes('perplexity')
      ? {
          webSearch: tool({
            description:
              'Search the web for recent news and current information. Use for recent events, news articles, or facts not in the RAG database.',
            inputSchema: z.object({
              query: z.string().describe('The search query'),
            }),
            execute: async (input) => {
              try {
                // Use Google Custom Search JSON API if available, otherwise DuckDuckGo lite
                const googleApiKey = process.env.GOOGLE_API_KEY;
                const googleCseId = process.env.GOOGLE_CSE_ID;

                if (googleApiKey && googleCseId) {
                  const url = `https://www.googleapis.com/customsearch/v1?key=${googleApiKey}&cx=${googleCseId}&q=${encodeURIComponent(input.query)}&num=5&lr=lang_fr`;
                  const res = await fetch(url, { signal: AbortSignal.timeout(8000) });
                  if (res.ok) {
                    const json = await res.json();
                    const results = (json.items ?? []).map((item: any, idx: number) => ({
                      id: idx + 1,
                      title: item.title,
                      snippet: item.snippet,
                      url: item.link,
                    }));
                    return { results, count: results.length };
                  }
                }

                // Fallback: use DuckDuckGo instant answer API
                const ddgUrl = `https://api.duckduckgo.com/?q=${encodeURIComponent(input.query)}&format=json&no_html=1&skip_disambig=1`;
                const ddgRes = await fetch(ddgUrl, { signal: AbortSignal.timeout(8000) });
                if (ddgRes.ok) {
                  const ddgJson = await ddgRes.json();
                  const results: Array<{
                    id: number;
                    title: string;
                    snippet: string;
                    url: string;
                  }> = [];
                  if (ddgJson.Abstract) {
                    results.push({
                      id: 1,
                      title: ddgJson.Heading ?? input.query,
                      snippet: ddgJson.Abstract,
                      url: ddgJson.AbstractURL ?? '',
                    });
                  }
                  for (const topic of ddgJson.RelatedTopics?.slice(0, 4) ?? []) {
                    if (topic.Text) {
                      results.push({
                        id: results.length + 1,
                        title: topic.FirstURL?.split('/').pop() ?? '',
                        snippet: topic.Text,
                        url: topic.FirstURL ?? '',
                      });
                    }
                  }
                  return { results, count: results.length };
                }

                return { results: [], count: 0, error: 'Search API unavailable' };
              } catch (err) {
                console.error('[ai-chat] webSearch error:', err);
                return { results: [], count: 0, error: String(err) };
              }
            },
          }),
        }
      : {}),

    // ── Widget / chart rendering ─────────────────────────────────────────────
    ...(features.includes('widgets')
      ? {
          renderWidget: tool({
            description:
              'Render an interactive chart or visualization. Use to compare party positions, show voting statistics, display poll data, or visualize any structured data. Returns chart configuration that the frontend renders.',
            inputSchema: z.object({
              title: z.string().describe('Chart title'),
              chartType: z
                .enum(['bar', 'pie', 'radar', 'line'])
                .describe('Type of chart: bar (comparison), pie (distribution), radar (multi-axis), line (trends)'),
              data: z
                .array(
                  z.object({
                    label: z.string().describe('Data point label (e.g. party name, category)'),
                    value: z.number().describe('Numeric value'),
                    color: z
                      .string()
                      .optional()
                      .describe('Optional hex color (e.g. #FF0000)'),
                  }),
                )
                .describe('Array of data points to visualize'),
              xAxisLabel: z.string().optional().describe('X-axis label'),
              yAxisLabel: z.string().optional().describe('Y-axis label'),
            }),
            execute: async (input) => ({
              widget: {
                type: 'chart',
                chartType: input.chartType,
                title: input.title,
                data: input.data,
                xAxisLabel: input.xAxisLabel,
                yAxisLabel: input.yAxisLabel,
              },
            }),
          }),
        }
      : {}),

    // ── Always-on tools ──────────────────────────────────────────────────────
    suggestFollowUps: tool({
      description: 'Generate 3 follow-up question suggestions for the user.',
      inputSchema: z.object({
        suggestions: z
          .array(z.string())
          .length(3)
          .describe('Exactly 3 follow-up question suggestions'),
      }),
      execute: async (input) => {
        return { suggestions: input.suggestions };
      },
    }),

    changeCity: tool({
      description:
        "Change the user's municipality/city context. Use when user asks to switch city or change location.",
      inputSchema: z.object({
        cityName: z.string().describe('The name of the city to switch to'),
        municipalityCode: z
          .string()
          .optional()
          .describe('The INSEE municipality code if known'),
      }),
      execute: async (input) => {
        let code = input.municipalityCode;

        // Look up municipality code from city name if not provided
        if (!code) {
          try {
            const snap = await db
              .collection('municipalities')
              .where('nom', '==', input.cityName)
              .limit(1)
              .get();
            if (snap.empty) {
              // Try case-insensitive by uppercasing
              const snap2 = await db
                .collection('municipalities')
                .where('nom', '>=', input.cityName.charAt(0).toUpperCase() + input.cityName.slice(1).toLowerCase())
                .where('nom', '<=', input.cityName.charAt(0).toUpperCase() + input.cityName.slice(1).toLowerCase() + '\uf8ff')
                .limit(1)
                .get();
              if (!snap2.empty) {
                const data = snap2.docs[0].data();
                code = (data.code as string) ?? snap2.docs[0].id;
              }
            } else {
              const data = snap.docs[0].data();
              code = (data.code as string) ?? snap.docs[0].id;
            }
          } catch (err) {
            console.error('[ai-chat] changeCity lookup failed:', err);
          }
        }

        return {
          action: 'changeCity',
          cityName: input.cityName,
          municipalityCode: code,
        };
      },
    }),

    changeCandidates: tool({
      description:
        'Update selected candidates/parties. Use when user asks to focus on specific parties or remove parties.',
      inputSchema: z.object({
        partyIds: z.array(z.string()).describe('The party IDs to set, add, or remove'),
        operation: z
          .enum(['set', 'add', 'remove'])
          .describe('Whether to set, add to, or remove from current selection'),
      }),
      execute: async (input) => {
        return {
          action: 'changeCandidates',
          partyIds: input.partyIds,
          operation: input.operation,
        };
      },
    }),

    removeRestrictions: tool({
      description:
        'Remove municipality/party restrictions for a broader national search. Use when user wants to search across all parties or remove city filter.',
      inputSchema: z.object({
        reason: z.string().describe('Brief reason why the user wants to broaden scope'),
      }),
      execute: async (input) => {
        return { action: 'removeRestrictions', reason: input.reason };
      },
    }),
  };
}

// ── Rate limiting (in-memory, per Vercel function instance) ────────────────
const RATE_LIMIT_WINDOW_MS = 60_000;
const RATE_LIMIT_MAX = 20;
const rateLimitMap = new Map<string, { count: number; resetAt: number }>();

function checkRateLimit(uid: string): boolean {
  const now = Date.now();
  const entry = rateLimitMap.get(uid);
  if (!entry || now > entry.resetAt) {
    rateLimitMap.set(uid, { count: 1, resetAt: now + RATE_LIMIT_WINDOW_MS });
    return true;
  }
  if (entry.count >= RATE_LIMIT_MAX) return false;
  entry.count++;
  return true;
}

const CHAT_ID_REGEX = /^[a-zA-Z0-9_-]{1,128}$/;

export async function POST(req: Request) {
  // ── Auth: verify Firebase ID token (optional — anonymous users allowed) ──
  const authHeader = req.headers.get('authorization');
  const token = authHeader?.startsWith('Bearer ') ? authHeader.slice(7) : null;
  let uid: string = 'anonymous';
  if (token) {
    try {
      const decoded = await auth.verifyIdToken(token);
      uid = decoded.uid;
    } catch {
      // Invalid token — fall through as anonymous rather than blocking
      console.warn('[ai-chat] Invalid auth token, proceeding as anonymous');
    }
  }

  // ── Rate limit (by uid or IP for anonymous) ─────────────────────────────
  const rateLimitKey = uid !== 'anonymous' ? uid : (req.headers.get('x-forwarded-for') ?? 'unknown');
  if (!checkRateLimit(rateLimitKey)) {
    return new Response(JSON.stringify({ error: 'Rate limit exceeded' }), { status: 429 });
  }

  const {
    messages: uiMessages,
    partyIds,
    locale,
    chatId,
    municipalityCode,
    enabledFeatures,
  } = (await req.json()) as {
    messages: UIMessage[];
    partyIds?: string[];
    locale?: string;
    chatId?: string;
    municipalityCode?: string;
    enabledFeatures?: string[];
  };

  console.log('[ai-chat] POST', { chatId, municipalityCode, partyIds, enabledFeatures, locale, uid, msgCount: uiMessages?.length });

  // ── Validate chatId format ──────────────────────────────────────────────
  if (chatId && !CHAT_ID_REGEX.test(chatId)) {
    return new Response(JSON.stringify({ error: 'Invalid chatId format' }), { status: 400 });
  }

  const messages = await convertToModelMessages(uiMessages ?? []);

  const currentDate = new Date().toLocaleDateString('fr-FR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

  let resolvedPartyIds = partyIds ?? [];
  let candidateContext = '';
  let candidateIds: string[] = [];
  let allCandidatesData: Array<{ id: string; [key: string]: any }> = [];

  if (municipalityCode) {
    try {
      const candidatesSnap = await db
        .collection('candidates')
        .where('municipality_code', '==', municipalityCode)
        .get();

      const candidates = candidatesSnap.docs.map((doc) => ({
        id: doc.id,
        ...doc.data(),
      }));
      allCandidatesData = candidates;

      console.log('[ai-chat] municipalityCode:', municipalityCode, 'partyIds:', partyIds, 'candidates found:', candidates.length);

      if (candidates.length > 0) {
        // Extract unique party IDs from candidates if none provided
        if (resolvedPartyIds.length === 0) {
          resolvedPartyIds = [
            ...new Set(candidates.flatMap((c: any) => c.party_ids ?? []).filter(Boolean)),
          ];
        }

        // Collect candidate IDs for search instructions
        candidateIds = candidates.map((c: any) => c.id);

        // Fetch party details for richer context
        const partiesSnap = await db.collection('parties').get();
        const partiesMap = new Map<string, any>();
        for (const doc of partiesSnap.docs) {
          partiesMap.set(doc.id, { id: doc.id, ...doc.data() });
        }

        // Build rich candidate context for system prompt
        candidateContext =
          `\n\n# Candidats disponibles dans cette commune (${municipalityCode})\n` +
          candidates
            .map((c: any) => {
              const name = [c.first_name, c.last_name].filter(Boolean).join(' ') || c.id;
              const partyNames = (c.party_ids ?? [])
                .map((pid: string) => partiesMap.get(pid)?.name ?? pid)
                .join(', ');
              const lines = [`## ${name}`];
              lines.push(`- **ID candidat (pour searchCandidateWebsite)**: \`${c.id}\``);
              lines.push(`- **Parti(s)**: ${partyNames || 'Indépendant'}`);
              if (c.position) lines.push(`- **Position**: ${c.position}`);
              if (c.bio) lines.push(`- **Bio**: ${c.bio}`);
              if (c.website_url) lines.push(`- **Site web**: ${c.website_url}`);
              if (c.manifesto_pdf_url) lines.push(`- **Profession de foi / PDF programme**: ${c.manifesto_pdf_url}`);
              if (c.is_incumbent) lines.push(`- **Sortant**: oui`);
              if (c.birth_year) lines.push(`- **Année de naissance**: ${c.birth_year}`);
              return lines.join('\n');
            })
            .join('\n\n');
      }
    } catch (err) {
      console.error('[ai-chat] Failed to resolve candidates:', err);
    }
  }

  const partiesList =
    resolvedPartyIds.length > 0 ? resolvedPartyIds.join(', ') : 'non spécifiés';
  const respondInLanguage =
    locale === 'en'
      ? 'Respond in English.'
      : "Réponds en français, en utilisant \"tu\" pour t'adresser à l'utilisateur.";

  // Determine which candidates to search based on user selection
  const hasSelection = (partyIds ?? []).length > 0;

  // Build selected candidate IDs from partyIds mapping (reuse already-fetched data)
  let searchCandidateIds: string[] = [];
  if (municipalityCode && candidateIds.length > 0) {
    if (hasSelection) {
      // Only search candidates whose party_ids overlap with selected partyIds
      searchCandidateIds = allCandidatesData
        .filter((c: any) => (c.party_ids ?? []).some((pid: string) => (partyIds ?? []).includes(pid)))
        .map((c: any) => c.id);
      // Fallback: if no match found, search all
      if (searchCandidateIds.length === 0) searchCandidateIds = candidateIds;
    } else {
      // No selection → search all candidates
      searchCandidateIds = candidateIds;
    }
  }

  const candidateIdsList = searchCandidateIds.map((id) => `  - candidateId: "${id}"`).join('\n');

  // When candidateIds is empty (no candidates found for this municipality),
  // fall back to party manifesto search to avoid referencing unavailable tools
  const hasCandidates = candidateIds.length > 0;
  console.log('[ai-chat] routing:', { municipalityCode, hasCandidates, hasSelection, candidateCount: candidateIds.length, searchCandidateCount: searchCandidateIds.length, resolvedPartyIds });

  const searchInstructions = municipalityCode && hasCandidates
    ? hasSelection && searchCandidateIds.length <= 3
      ? `# RÈGLE CRITIQUE — OBLIGATOIRE
Pour TOUTE question politique, tu DOIS appeler searchCandidateWebsite pour CHAQUE candidat sélectionné ci-dessous AVANT de répondre.
N'utilise PAS searchPartyManifesto en mode commune.
Ne réponds JAMAIS sans avoir d'abord appelé les outils de recherche.
L'utilisateur a sélectionné ces candidats via l'interface — concentre-toi sur eux.

Appelle searchCandidateWebsite avec ces candidateId (un appel par candidat) :
${candidateIdsList}`
      : `# RÈGLE CRITIQUE — OBLIGATOIRE
Pour TOUTE question politique, tu DOIS appeler searchAllCandidates avec ta requête AVANT de répondre.
Cet outil recherche automatiquement dans TOUS les candidats de la commune et re-classe les résultats par pertinence.
N'utilise PAS searchPartyManifesto en mode commune.
Ne réponds JAMAIS sans avoir d'abord appelé searchAllCandidates.
Ne demande JAMAIS à l'utilisateur de préciser quel candidat ou quel parti.

${hasSelection ? `L'utilisateur a sélectionné des candidats — mets en avant leurs positions, mais inclus aussi les autres pour comparaison.` : `Aucun candidat sélectionné — présente les positions de TOUS les candidats de la commune.`}

Candidats disponibles :
${candidateIds.map((id) => `  - ${id}`).join('\n')}`
    : `# RÈGLE CRITIQUE — OBLIGATOIRE
Pour TOUTE question politique, tu DOIS appeler searchPartyManifesto pour CHAQUE parti ci-dessous AVANT de répondre.
Ne réponds JAMAIS sans avoir d'abord appelé les outils de recherche.
Ne demande JAMAIS à l'utilisateur de préciser quel parti — cherche dans TOUS.

Appelle searchPartyManifesto avec ces partyId (un appel par parti) :
${resolvedPartyIds.map((id) => `  - partyId: "${id}"`).join('\n') || '  (aucun parti trouvé)'}`;

  const contextLine = municipalityCode
    ? `L'utilisateur consulte les candidats de la commune ${municipalityCode}. ${hasSelection ? `Candidats sélectionnés : ${searchCandidateIds.join(', ')}` : 'Aucun candidat sélectionné — montre TOUS les candidats.'}`
    : `L'utilisateur a sélectionné ces partis : ${partiesList}`;

  const systemPrompt = `${searchInstructions}

# Rôle
Tu es un assistant IA politiquement neutre spécialisé dans les élections municipales françaises.
Tu aides les citoyens à comparer les positions des candidats de leur commune en te basant sur leurs programmes, sites web et professions de foi.

# Contexte
Date : ${currentDate}
${contextLine}

# Instructions pour ta réponse
1. **Basé sur les sources** : Réfère-toi exclusivement aux documents récupérés via les outils. Si les documents ne contiennent pas d'information sur le sujet, dis-le honnêtement. N'invente jamais de faits.
2. **Neutralité stricte** : N'évalue pas les positions. Évite les adjectifs subjectifs. Ne donne AUCUNE recommandation de vote.
3. **Comparatif par défaut** : Quand plusieurs candidats ont des positions sur un sujet, présente-les côte à côte pour faciliter la comparaison. Utilise des tableaux ou puces par candidat.
4. **Style de réponse** :
   - Concret et facile à comprendre, avec des chiffres précis quand disponibles
   - Cite les sources : [1], [2] après chaque affirmation factuelle
   - Si aucune source n'a été utilisée, écris l'affirmation en italique
   - Formate en Markdown avec des puces et des mots-clés en gras
   - Réponses concises : 1-3 puces par candidat, sauf demande de détails
   - **Sois proactif** : ne pose pas plus d'une question de clarification. Si la demande est vague, fais des choix raisonnables et agis. Montre ce que tu sais faire.
5. **Limites** : Signale quand l'information peut être obsolète ou incomplète
6. **Protection des données** : Ne demande pas d'intentions de vote ni de données personnelles
7. **Suggestions de suivi** : À la fin de CHAQUE réponse, appelle TOUJOURS l'outil suggestFollowUps avec 3 questions pertinentes
8. **Reformulation des requêtes** : Quand tu appelles un outil de recherche, ton paramètre "query" doit être AUTONOME et COMPLET. N'utilise JAMAIS de pronoms ("ça", "ce sujet", "celui-là") ni de références à des messages précédents. Inclus tout le contexte nécessaire directement dans la requête. Exemple : au lieu de "et sur ce sujet ?", écris "positions des candidats sur les transports en commun à Marseille". Garde les requêtes concises mais auto-suffisantes.

Tu disposes d'une recherche approfondie automatique : si tes premières recherches ne trouvent pas assez de résultats, le système relance automatiquement des recherches plus larges. Fais confiance aux résultats retournés par tes outils.

${respondInLanguage}${candidateContext}`;

  // Model fallback: Gemini 2.5 Flash (primary) → Scaleway Qwen3 235B (fallback)
  let model: LanguageModel = google('gemini-2.5-flash');
  try {
    // Test that the Google provider is configured (key present)
    if (!process.env.GOOGLE_GENERATIVE_AI_API_KEY) {
      console.warn('[ai-chat] GOOGLE_GENERATIVE_AI_API_KEY missing, falling back to Scaleway');
      model = scalewayChat;
    }
  } catch {
    console.warn('[ai-chat] Google provider init failed, falling back to Scaleway');
    model = scalewayChat;
  }

  const result = streamText({
    model,
    system: systemPrompt,
    messages,
    stopWhen: stepCountIs(6),
    toolChoice: 'auto',
    onError({ error }) {
      console.error('[ai-chat] streamText error:', error);
    },
    onStepFinish({ stepNumber, toolCalls, finishReason, usage }) {
      console.log('[ai-chat:step]', {
        chatId,
        stepNumber,
        toolCalls: toolCalls?.map((t) => t?.toolName),
        finishReason,
        usage,
      });
    },
    async onFinish({ text, usage }) {
      // Persist conversation to Firestore (fire-and-forget, never blocks the response)
      if (!chatId) return;
      try {
        const now = new Date().toISOString();
        const chatRef = db.collection('ai_sdk_chats').doc(chatId);
        const doc = await chatRef.get();

        // Build a slim message pair from the latest exchange
        const lastUserMsg = uiMessages.filter((m) => m.role === 'user').at(-1);
        const newMessages = [
          ...(lastUserMsg ? [{ role: 'user' as const, content: lastUserMsg.parts?.map((p) => ('text' in p ? p.text : '')).join('') ?? '', timestamp: now }] : []),
          { role: 'assistant' as const, content: text, timestamp: now },
        ];

        if (doc.exists) {
          // Append messages to existing conversation
          const data = doc.data()!;
          const existing = (data.messages as any[]) ?? [];
          await chatRef.update({
            messages: [...existing, ...newMessages],
            updated_at: now,
            municipality_code: municipalityCode ?? data.municipality_code ?? null,
            party_ids: resolvedPartyIds.length > 0 ? resolvedPartyIds : data.party_ids ?? [],
            total_tokens: (data.total_tokens ?? 0) + (usage?.totalTokens ?? 0),
          });
        } else {
          // Create new conversation document
          await chatRef.set({
            messages: newMessages,
            municipality_code: municipalityCode ?? null,
            party_ids: resolvedPartyIds,
            locale: locale ?? 'fr',
            enabled_features: enabledFeatures ?? [],
            created_at: now,
            updated_at: now,
            total_tokens: usage?.totalTokens ?? 0,
          });
        }
      } catch (err) {
        console.error('[ai-chat] Failed to persist conversation:', err);
      }
    },
    tools: buildTools(enabledFeatures, candidateIds),
  });

  return result.toUIMessageStreamResponse();
}
