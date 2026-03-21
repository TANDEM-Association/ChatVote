import { google } from '@ai-sdk/google';
import { type UIMessage, type LanguageModel, convertToModelMessages, hasToolCall, stepCountIs, tool } from 'ai';
import { after } from 'next/server';
import { observe, propagateAttributes, getActiveTraceId } from '@langfuse/tracing';
import { langfuseSpanProcessor } from '@lib/ai/langfuse-processor';
import { Langfuse } from 'langfuse';
import { streamText } from '@lib/ai/tracing';
import { z } from 'zod/v4';

import { deepResearch } from '@lib/ai/deep-research';
import { embedQuery } from '@lib/ai/embedding';
import { COLLECTIONS } from '@lib/ai/qdrant-client';
import { expandSearchQueries } from '@lib/ai/query-expansion';
import { rerankResults } from '@lib/ai/rerank';
import {
  type SearchResult,
  searchQdrant,
  searchQdrantBroad,
  searchQdrantRaw,
  deduplicateResults,
} from '@lib/ai/qdrant-search';
import { scalewayChat } from '@lib/ai/providers';
import { db, auth } from '@lib/firebase/firebase-admin';
import { getAiConfig } from '@lib/ai/ai-config';

export const maxDuration = 120;
export const preferredRegion = 'cdg1';

// Module-level Langfuse SDK client for trace-level I/O updates
// (OTEL setActiveTraceIO doesn't populate trace I/O with LangfuseSpanProcessor)
const langfuse = process.env.LANGFUSE_SECRET_KEY ? new Langfuse() : null;

// ── data.gouv.fr REST API client ─────────────────────────────────────────────
// Uses the official data.gouv.fr REST API (https://www.data.gouv.fr/api/1/)
// Public endpoint, no API key required
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

async function searchDataGouv(query: string, limit = 5): Promise<DataGouvDataset[]> {
  const apiUrl = `https://www.data.gouv.fr/api/1/datasets/?q=${encodeURIComponent(query)}&page_size=${limit}`;
  console.log('[data.gouv] Searching:', query);
  const res = await fetch(apiUrl, { signal: AbortSignal.timeout(8000) });
  if (!res.ok) throw new Error(`data.gouv.fr API returned ${res.status}`);
  const json = await res.json();
  const results = (json.data ?? []).map((d: any) => ({
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
  console.log(`[data.gouv] Found ${results.length} datasets for "${query}"`);
  return results;
}


function buildTools(enabledFeatures: string[] | undefined, candidateIds: string[] = [], _candidateNames: Map<string, string> = new Map(), selectedCandidateIds: string[] = [], aiConfig = { maxSearchCalls: 3, docsPerCandidateShallow: 3, docsPerCandidateDeep: 5, docsPerSearchShallow: 6, docsPerSearchDeep: 8, scoreThreshold: 0.25 as number }) {
  const features = enabledFeatures ?? ['rag'];
  const ragEnabled = features.includes('rag');

  // Global source counter — shared across ALL tool calls so each source gets a
  // unique sequential number (e.g. tool call 1 → [1-5], tool call 2 → [6-10]).
  // This lets the LLM cite [1], [2], [3]… reliably without renumbering.
  let globalSourceCounter = 0;

  // Per-query dedup: cache by normalized query so different topics run separate
  // searches but duplicate/reformulated queries hit the cache.
  // Also tracks total calls to cap runaway models (Qwen3).
  const searchCache = new Map<string, Promise<{ results: SearchResult[]; count: number }>>();
  let searchCallCount = 0;
  const MAX_SEARCH_CALLS = aiConfig.maxSearchCalls; // allow up to N distinct topic searches per request



  /** Assign globally unique sequential IDs to search results */
  function assignGlobalIds<T>(results: T[]): (T & { id: number })[] {
    return results.map((r) => ({ ...r, id: ++globalSourceCounter }));
  }


  return {
    // ── RAG search tools (feature-gated) ────────────────────────────────────
    ...(ragEnabled
      ? {
          searchDocumentsWithRerank: tool({
            description:
              `Recherche dans les documents politiques (programmes, professions de foi, sites web) avec reformulation automatique et re-classement par pertinence PER-CANDIDAT pour une représentation équitable.

UN SEUL APPEL recherche dans TOUS les candidats en parallèle — ne fais PAS un appel par candidat.
La query doit être THÉMATIQUE (le sujet), JAMAIS le nom d'un candidat ou parti.

Exemples CORRECTS :
- searchDocumentsWithRerank({ query: "sécurité police municipale vidéoprotection" }) → cherche dans TOUS les candidats
- searchDocumentsWithRerank({ query: "logement rénovation thermique loyers" }) → tous les candidats
- searchDocumentsWithRerank({ query: "engagements programme propositions", depth: "deep" }) → analyse approfondie tous candidats
- searchDocumentsWithRerank({ query: "écologie transition énergétique", candidateIds: ["cand-63113-3"] }) → UN candidat ciblé uniquement

Exemples INCORRECTS (ne fais JAMAIS ça) :
- searchDocumentsWithRerank({ query: "Pierre BERNARD Rassemblement National programme" }) ← NOM dans query
- Appeler 5 fois pour 5 candidats différents ← UN appel suffit pour TOUS
- searchDocumentsWithRerank({ query: "programme engagements", candidateIds: ["cand-1","cand-2","cand-3","cand-4","cand-5"] }) ← inutile, sans candidateIds ça cherche déjà dans tous`,
            inputSchema: z.object({
              query: z.string().describe('Requête THÉMATIQUE : décris le sujet recherché, JAMAIS de noms de candidats/partis. Ex: "sécurité police municipale", "écologie transition énergétique"'),
              candidateIds: z
                .array(z.string())
                .optional()
                .describe('Filtrer par candidats (IDs fournis dans le contexte). Si omis et partyIds omis, recherche TOUS les candidats automatiquement. Passe UN SEUL candidat uniquement si l\'utilisateur demande spécifiquement les positions d\'un candidat précis.'),
              partyIds: z
                .array(z.string())
                .optional()
                .describe('Filtrer par partis (IDs fournis dans le contexte). Recherche dans les programmes/manifestes nationaux des partis.'),
              depth: z
                .enum(['shallow', 'deep'])
                .optional()
                .describe('shallow (défaut) : top 3 docs/candidat, rapide. deep : top 5 docs/candidat, plus complet. Utilise deep quand la question demande une analyse détaillée ou quand un seul candidat est ciblé.'),
            }),
            execute: async (input) => {
              const { query, candidateIds: filterCandidateIds, partyIds: filterPartyIds, depth = 'shallow' } = input;

              // Dedup by query: same query returns cached result, different queries run separate searches.
              const cacheKey = query.trim().toLowerCase();
              const cached = searchCache.get(cacheKey);
              if (cached) {
                if (process.env.NODE_ENV === 'development') {
                  console.log(`[searchDocumentsWithRerank] Cache hit for "${query.slice(0, 50)}"`);
                }
                return cached;
              }

              // Cap total distinct searches to prevent runaway models
              if (searchCallCount >= MAX_SEARCH_CALLS) {
                // Return the most recent cached result instead of running another search
                const lastResult = Array.from(searchCache.values()).pop();
                if (lastResult) {
                  if (process.env.NODE_ENV === 'development') {
                    console.log(`[searchDocumentsWithRerank] Max calls (${MAX_SEARCH_CALLS}) reached, returning last result`);
                  }
                  return lastResult;
                }
              }
              searchCallCount++;
              const docsPerCandidate = depth === 'deep' ? aiConfig.docsPerCandidateDeep : aiConfig.docsPerCandidateShallow;
              const docsPerSearch = depth === 'deep' ? aiConfig.docsPerSearchDeep : aiConfig.docsPerSearchShallow;

              const promise = (async () => {
                // Query expansion: generate 2-3 RAG-optimized variants
                const queries = await expandSearchQueries(query);

                // Pre-embed all expanded queries in parallel
                const vectors = await Promise.all(queries.map((q) => embedQuery(q)));
                const queryVectors = new Map(queries.map((q, i) => [q, vectors[i]]));

                // ── Search candidate documents (all queries × all candidates in parallel) ──
                const searchCids = filterCandidateIds?.map((id) => id.toLowerCase())
                  ?? ((!filterPartyIds || filterPartyIds.length === 0)
                    ? (selectedCandidateIds.length > 0 ? selectedCandidateIds : candidateIds)
                    : []);

                // Per-candidate results map for per-candidate reranking
                const perCandidateResults = new Map<string, SearchResult[]>();

                if (searchCids.length > 0) {
                  const candidateResults = await Promise.all(
                    searchCids.flatMap((cid) =>
                      queries.map((q) =>
                        searchQdrant(COLLECTIONS.candidatesWebsites, q, 'metadata.namespace', cid, docsPerSearch, queryVectors.get(q)!, { scoreThreshold: aiConfig.scoreThreshold })
                          .then((results) => ({ cid, results })),
                      ),
                    ),
                  );
                  // Group results by candidate
                  for (const { cid, results } of candidateResults) {
                    const existing = perCandidateResults.get(cid) ?? [];
                    existing.push(...results);
                    perCandidateResults.set(cid, existing);
                  }
                }

                // ── Search party manifesto documents ──
                const manifestoResults: SearchResult[] = [];
                const searchPids = filterPartyIds?.map((id) => id.toLowerCase()) ?? [];
                if (searchPids.length > 0) {
                  const partyResults = await Promise.all(
                    searchPids.flatMap((pid) =>
                      queries.map((q) =>
                        searchQdrant(COLLECTIONS.allParties, q, 'metadata.namespace', pid, docsPerSearch, queryVectors.get(q), { scoreThreshold: aiConfig.scoreThreshold }),
                      ),
                    ),
                  );
                  manifestoResults.push(...partyResults.flat());
                }

                if (perCandidateResults.size === 0 && manifestoResults.length === 0) {
                  return { results: [] as SearchResult[], count: 0, message: 'Aucun document trouvé pour ces filtres.' };
                }

                // ── Per-candidate dedup + rerank (like Python backend) ──
                const rerankedCandidateDocs: SearchResult[] = [];
                const rerankTasks: Array<Promise<SearchResult[]>> = [];
                const rerankCids: string[] = [];
                const smallGroups: SearchResult[] = [];

                for (const [cid, docs] of perCandidateResults) {
                  const deduped = deduplicateResults(docs);
                  if (deduped.length >= 3) {
                    rerankCids.push(cid);
                    rerankTasks.push(
                      rerankResults(deduped, query, docsPerCandidate).catch(() => deduped.slice(0, docsPerCandidate)),
                    );
                  } else {
                    smallGroups.push(...deduped);
                  }
                }

                if (rerankTasks.length > 0) {
                  const rerankResults_ = await Promise.all(rerankTasks);
                  for (const results of rerankResults_) {
                    rerankedCandidateDocs.push(...results);
                  }
                }
                rerankedCandidateDocs.push(...smallGroups);

                // ── Manifesto dedup + rerank (global, up to 10) ──
                let rerankedManifestoDocs: SearchResult[] = [];
                if (manifestoResults.length > 0) {
                  const dedupedManifestos = deduplicateResults(manifestoResults);
                  rerankedManifestoDocs = dedupedManifestos.length >= 3
                    ? await rerankResults(dedupedManifestos, query, Math.min(10, dedupedManifestos.length)).catch(() => dedupedManifestos.slice(0, 10))
                    : dedupedManifestos;
                }

                // ── Merge: candidate docs first, then manifestos ──
                const merged = assignGlobalIds([...rerankedCandidateDocs, ...rerankedManifestoDocs]);

                if (process.env.NODE_ENV === 'development') {
                  console.log(`[searchDocumentsWithRerank] ${queries.length} queries × ${searchCids.length}c+${searchPids.length}p | depth=${depth} | per-candidate: ${perCandidateResults.size} groups → ${rerankedCandidateDocs.length} docs | manifestos: ${manifestoResults.length} raw → ${rerankedManifestoDocs.length} | total: ${merged.length}`);
                }

                return { results: merged, count: merged.length };
              })();

              searchCache.set(cacheKey, promise);

              try {
                return await promise;
              } catch (err) {
                searchCache.delete(cacheKey); // allow retry on failure
                console.error('[ai-chat] searchDocumentsWithRerank error:', err);
                return { results: [] as SearchResult[], count: 0, error: String(err) };
              }
            },
          }),
        }
      : {}),

    // ── Voting records (Qdrant collection) ──────────────────────────────────
    ...(features.includes('voting-records')
      ? {
          searchVotingRecords: tool({
            description:
              "Recherche dans les votes de l'Assemblée nationale. Contient les scrutins publics avec le détail par groupe parlementaire (pour, contre, abstention). Utilise pour vérifier la cohérence entre les promesses d'un parti et ses votes passés, ou pour illustrer une position avec des faits concrets.",
            inputSchema: z.object({
              query: z.string().describe('Sujet, loi ou projet de loi à rechercher (ex: "loi climat résilience", "réforme retraites 2023")'),
            }),
            execute: async (input) => {
              try {
                // Query expansion: generate 2-3 RAG-optimized variants
                const queries = await expandSearchQueries(input.query);

                // Search with all expanded queries in parallel
                const allResults = await Promise.all(
                  queries.map((q) =>
                    searchQdrant(COLLECTIONS.votingBehavior, q, 'metadata.namespace', 'vote_summary', 8),
                  ),
                );
                let results = deduplicateResults(allResults.flat());

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
                const reranked = assignGlobalIds(await rerankResults(results, input.query, 8));
                return { results: reranked, count: reranked.length };
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
              "Recherche dans les questions parlementaires posées par les députés au gouvernement. Révèle les préoccupations concrètes des élus sur le terrain (santé, éducation, agriculture, emploi...). Utile pour montrer l'engagement réel d'un parti sur un sujet au-delà de son programme.",
            inputSchema: z.object({
              query: z.string().describe('Sujet à rechercher dans les questions parlementaires (ex: "déserts médicaux", "fermeture école rurale")'),
              partyId: z
                .string()
                .optional()
                .describe('Optionnel : filtrer par parti pour voir ses questions spécifiques'),
            }),
            execute: async (input) => {
              const namespace = input.partyId
                ? `${input.partyId}-parliamentary-questions`
                : undefined;
              try {
                // Query expansion: generate 2-3 RAG-optimized variants
                const queries = await expandSearchQueries(input.query);

                // Search with all expanded queries in parallel
                const allResults = await Promise.all(
                  queries.map(async (q) => {
                    if (namespace) {
                      return searchQdrant(
                        COLLECTIONS.parliamentaryQuestions, q,
                        'metadata.namespace', namespace, 8,
                        undefined, { mustNot: null },
                      );
                    } else {
                      return searchQdrantRaw(COLLECTIONS.parliamentaryQuestions, q, 8);
                    }
                  }),
                );
                let results = deduplicateResults(allResults.flat());
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
                const reranked = assignGlobalIds(await rerankResults(results, input.query, 8));
                return { partyId: input.partyId, results: reranked, count: reranked.length };
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
              "Recherche dans les données ouvertes de l'État français (data.gouv.fr). Contient des jeux de données officiels : budgets municipaux, démographie INSEE, résultats électoraux, équipements publics, qualité de l'air, etc. Utilise pour appuyer une réponse avec des chiffres vérifiables ou quand l'utilisateur demande des statistiques.",
            inputSchema: z.object({
              query: z.string().describe('Recherche en français (ex: "budget commune Marseille", "résultats élections municipales 2020")'),
            }),
            execute: async (input) => {
              try {
                const datasets = await searchDataGouv(input.query, 5);
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
              "Recherche web pour l'actualité récente et les informations non présentes dans la base documentaire. Utilise pour : actualités de campagne, déclarations récentes, sondages, événements locaux, faits divers liés à la commune. Complément aux outils RAG, pas un substitut.",
            inputSchema: z.object({
              query: z.string().describe('Recherche web en français — privilégie des termes précis et datés si possible'),
            }),
            execute: async (input) => {
              try {
                const perplexityKey = process.env.PERPLEXITY_API_KEY;
                if (perplexityKey) {
                  // Use Perplexity Sonar API for web search
                  const res = await fetch('https://api.perplexity.ai/chat/completions', {
                    method: 'POST',
                    headers: {
                      'Authorization': `Bearer ${perplexityKey}`,
                      'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                      model: 'sonar',
                      messages: [
                        { role: 'system', content: 'Tu es un assistant de recherche web. Réponds en français avec des faits précis et sourcés. Cite les URLs des sources.' },
                        { role: 'user', content: input.query },
                      ],
                    }),
                    signal: AbortSignal.timeout(15000),
                  });
                  if (res.ok) {
                    const json = await res.json();
                    const content = json.choices?.[0]?.message?.content ?? '';
                    const citations = (json.citations ?? []) as string[];
                    const results = citations.map((url: string, idx: number) => ({
                      id: idx + 1,
                      title: url.replace(/^https?:\/\/(www\.)?/, '').split('/')[0],
                      snippet: '',
                      url,
                    }));
                    // Add the main response as first result if no citations
                    if (results.length === 0 && content) {
                      results.push({ id: 1, title: 'Résultat Perplexity', snippet: content.slice(0, 500), url: '' });
                    }
                    return { results, count: results.length, summary: content };
                  }
                }

                // Fallback: DuckDuckGo instant answer API
                const ddgUrl = `https://api.duckduckgo.com/?q=${encodeURIComponent(input.query)}&format=json&no_html=1&skip_disambig=1`;
                const ddgRes = await fetch(ddgUrl, { signal: AbortSignal.timeout(8000) });
                if (ddgRes.ok) {
                  const ddgJson = await ddgRes.json();
                  const results: Array<{ id: number; title: string; snippet: string; url: string }> = [];
                  if (ddgJson.Abstract) {
                    results.push({ id: 1, title: ddgJson.Heading ?? input.query, snippet: ddgJson.Abstract, url: ddgJson.AbstractURL ?? '' });
                  }
                  for (const topic of ddgJson.RelatedTopics?.slice(0, 4) ?? []) {
                    if (topic.Text) {
                      results.push({ id: results.length + 1, title: topic.FirstURL?.split('/').pop() ?? '', snippet: topic.Text, url: topic.FirstURL ?? '' });
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
              "Affiche un graphique interactif. Utilise pour comparer visuellement les positions des candidats, montrer des statistiques de vote, ou visualiser des données structurées. Particulièrement utile quand tu as des données chiffrées à comparer (budgets, pourcentages, scores). Le frontend gère le rendu — tu fournis les données.",
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
      description: "Génère 3 suggestions de questions de suivi pertinentes et concrètes. Les suggestions doivent approfondir le sujet discuté, explorer un angle connexe, ou comparer avec d'autres candidats/thèmes. Appelle cet outil à la FIN de chaque réponse. N'écris JAMAIS les suggestions en texte — utilise TOUJOURS cet outil.",
      inputSchema: z.object({
        suggestions: z
          .array(z.string())
          .length(3)
          .describe('3 questions de suivi : une qui approfondit, une qui compare, une qui explore un thème connexe'),
      }),
      execute: async (input) => {
        return { suggestions: input.suggestions };
      },
    }),

    presentOptions: tool({
      description: "Affiche des options cliquables pour l'utilisateur. Utilise au lieu d'écrire une liste numérotée ou des questions dans le texte. Mets la question dans le champ 'label' et les choix dans 'options'. N'écris PAS ces éléments dans ton texte — l'outil les affiche automatiquement comme des boutons.",
      inputSchema: z.object({
        label: z.string().optional().describe('Titre optionnel au-dessus des options (ex : "Quel sujet t\'intéresse ?")'),
        options: z
          .array(z.string())
          .min(2)
          .max(8)
          .describe('Les options à présenter comme boutons cliquables'),
      }),
      execute: async (input) => {
        return { label: input.label, options: input.options };
      },
    }),

    runDeepResearch: tool({
      description: "Recherche approfondie multi-sources. **N'utilise cet outil QUE si l'utilisateur demande EXPLICITEMENT une analyse approfondie** (ex: 'analyse en profondeur', 'recherche complète'). Pour les questions normales, searchDocumentsWithRerank suffit — il gère déjà la reformulation et le re-classement.",
      inputSchema: z.object({
        query: z.string().describe('Le sujet à approfondir — la requête originale de l\'utilisateur'),
        collections: z.array(z.string()).optional().describe('Collections cibles (optionnel — par défaut toutes)'),
      }),
      execute: async (input) => {
        const start = Date.now();
        const collections = input.collections?.length
          ? input.collections
          : [COLLECTIONS.candidatesWebsites, COLLECTIONS.allParties];
        const result = await deepResearch({
          originalQuery: input.query,
          collections,
          candidateIds: selectedCandidateIds.length > 0 ? selectedCandidateIds : candidateIds.length > 0 ? candidateIds : undefined,
        });
        const elapsed = Date.now() - start;
        const findings = assignGlobalIds(result.findings.slice(0, 12).map((r) => ({
            content: r.content.slice(0, 300),
            source: r.source,
            url: r.url,
            score: r.score,
            party_id: r.party_id,
            candidate_name: r.candidate_name,
          })));
        return {
          findings,
          totalFindings: result.findings.length,
          queriesTried: result.queriesTried,
          collectionsSearched: result.collectionsSearched,
          summary: result.summary,
          elapsedMs: elapsed,
        };
      },
    }),

    changeCity: tool({
      description:
        `Change la commune de l'utilisateur. Utilise quand l'utilisateur mentionne une autre ville ou demande à changer de commune.
IMPORTANT : Après changeCity, NE FAIS PAS de searchDocumentsWithRerank dans le même tour — les candidats ne seront mis à jour qu'au prochain message. Annonce le changement et propose des questions à l'utilisateur via suggestFollowUps.`,
      inputSchema: z.object({
        cityName: z.string().describe('Nom de la commune (ex: "Marseille", "Lyon 3e")'),
        municipalityCode: z
          .string()
          .optional()
          .describe('Code INSEE si connu (ex: "13055" pour Marseille) — sinon le système le résout automatiquement'),
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

        // Fetch candidates for the new city so the LLM knows who's available
        let newCandidates: Array<{ id: string; name: string; party_ids: string[] }> = [];
        if (code) {
          try {
            const candidatesSnap = await db
              .collection('candidates')
              .where('municipality_code', '==', code)
              .get();
            newCandidates = candidatesSnap.docs.map((d) => {
              const data = d.data();
              return {
                id: d.id,
                name: `${data.first_name ?? ''} ${data.last_name ?? ''}`.trim(),
                party_ids: data.party_ids ?? [],
              };
            });
          } catch (err) {
            console.error('[ai-chat] changeCity candidate fetch failed:', err);
          }
        }

        return {
          action: 'changeCity',
          cityName: input.cityName,
          municipalityCode: code,
          candidates: newCandidates,
          message: newCandidates.length > 0
            ? `Commune changée pour ${input.cityName} (${code}). ${newCandidates.length} candidats disponibles : ${newCandidates.map((c) => c.name).join(', ')}. Les recherches utiliseront ces candidats au prochain message.`
            : `Commune changée pour ${input.cityName} (${code}). Aucun candidat trouvé pour cette commune.`,
        };
      },
    }),

    changeCandidates: tool({
      description:
        "Modifie la sélection de candidats/partis de l'utilisateur. Utilise quand l'utilisateur veut se concentrer sur certains partis, en ajouter ou en retirer de la comparaison.",
      inputSchema: z.object({
        partyIds: z.array(z.string()).describe('IDs des partis à ajouter, définir ou retirer'),
        operation: z
          .enum(['set', 'add', 'remove'])
          .describe('"set" remplace la sélection, "add" ajoute, "remove" retire'),
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
        "Supprime les filtres de commune ou de parti pour élargir la recherche au niveau national. Utilise quand l'utilisateur veut comparer au-delà de sa commune ou chercher des informations sur des partis non présents localement.",
      inputSchema: z.object({
        reason: z.string().describe("Raison de l'élargissement (ex: \"l'utilisateur veut comparer avec d'autres villes\")"),
      }),
      execute: async (input) => {
        return { action: 'removeRestrictions', reason: input.reason };
      },
    }),
  };
}

// ── Rate limiting (in-memory, per Vercel function instance) ────────────────
const RATE_LIMIT_WINDOW_MS = 60_000;
const rateLimitMap = new Map<string, { count: number; resetAt: number }>();

function checkRateLimit(uid: string, rateLimitMax: number): boolean {
  const now = Date.now();
  const entry = rateLimitMap.get(uid);
  if (!entry || now > entry.resetAt) {
    rateLimitMap.set(uid, { count: 1, resetAt: now + RATE_LIMIT_WINDOW_MS });
    return true;
  }
  if (entry.count >= rateLimitMax) return false;
  entry.count++;
  return true;
}

const CHAT_ID_REGEX = /^[a-zA-Z0-9_-]{1,128}$/;

const handleChat = observe(async function handleChat(req: Request) {
  // ── Load AI config (cached, falls back to defaults) ──────────────────────
  const aiConfig = await getAiConfig();

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
  if (!checkRateLimit(rateLimitKey, aiConfig.rateLimitMax)) {
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

  // Apply admin config overrides to features
  const featureMap: Record<string, boolean> = {
    rag: aiConfig.enableRag,
    perplexity: aiConfig.enablePerplexity,
    'data-gouv': aiConfig.enableDataGouv,
    widgets: aiConfig.enableWidgets,
    'voting-records': aiConfig.enableVotingRecords,
    parliamentary: aiConfig.enableParliamentary,
  };
  let resolvedFeatures = Object.entries(featureMap)
    .filter(([, enabled]) => enabled)
    .map(([id]) => id);

  console.log('[ai-chat] POST', { chatId, municipalityCode, partyIds, enabledFeatures, locale, uid, msgCount: uiMessages?.length });

  // ── Langfuse: set trace-level input via SDK (OTEL setActiveTraceIO doesn't populate trace I/O) ──
  const lastUserMessage = uiMessages?.[uiMessages.length - 1];
  const inputText = lastUserMessage?.parts
    ?.filter((p): p is { type: 'text'; text: string } => p.type === 'text')
    .map((p) => p.text)
    .join('') ?? '';
  const langfuseTraceId = getActiveTraceId();
  if (langfuse && langfuseTraceId) {
    langfuse.trace({
      id: langfuseTraceId,
      input: inputText,
      sessionId: chatId ?? undefined,
      userId: uid,
    });
  }

  // ── Validate chatId format ──────────────────────────────────────────────
  if (chatId && !CHAT_ID_REGEX.test(chatId)) {
    return new Response(JSON.stringify({ error: 'Invalid chatId format' }), { status: 400 });
  }

  // ── Langfuse: propagate session/user to all child OTel spans ──────────
  return propagateAttributes(
    {
      sessionId: chatId ?? undefined,
      userId: uid,
      traceName: 'ai-chat',
      tags: municipalityCode ? ['municipal', municipalityCode] : undefined,
    },
    async () => {

  const messages = await convertToModelMessages(uiMessages ?? []);

  const currentDate = new Date().toLocaleDateString('fr-FR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

  let resolvedPartyIds = partyIds ?? [];
  let candidateContext = '';
  let candidateIds: string[] = [];
  const candidateNamesMap = new Map<string, string>();
  let allCandidatesData: Array<{ id: string; [key: string]: any }> = [];
  let municipalityName: string | undefined;

  if (municipalityCode) {
    try {
      // Fetch municipality name and candidates in parallel
      const [municipalitySnap, candidatesSnap] = await Promise.all([
        db.collection('municipalities').where('code', '==', municipalityCode).limit(1).get(),
        db.collection('candidates').where('municipality_code', '==', municipalityCode).get(),
      ]);
      if (!municipalitySnap.empty) {
        municipalityName = (municipalitySnap.docs[0].data().nom as string | undefined) ?? municipalityCode;
      }

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

        // Collect candidate IDs and build name lookup for search instructions
        candidateIds = candidates.map((c: any) => c.id);
        for (const c of candidates as any[]) {
          const name = [c.first_name, c.last_name].filter(Boolean).join(' ');
          if (name) candidateNamesMap.set(String(c.id).toLowerCase(), name);
        }

        // Fetch party details for richer context
        const partiesSnap = await db.collection('parties').get();
        const partiesMap = new Map<string, any>();
        for (const doc of partiesSnap.docs) {
          partiesMap.set(doc.id, { id: doc.id, ...doc.data() });
        }

        // Build rich candidate context for system prompt — only selected candidates when user has a selection
        // Note: candidate IDs are internal identifiers for tool calls only — never show them to the user
        const selectedPartySet = new Set(partyIds ?? []);
        const contextCandidates = selectedPartySet.size > 0
          ? candidates.filter((c: any) => (c.party_ids ?? []).some((pid: string) => selectedPartySet.has(pid)))
          : candidates;
        candidateContext =
          `\n\n# Candidats ${selectedPartySet.size > 0 ? 'sélectionnés' : 'disponibles'} dans cette commune (${municipalityName ?? municipalityCode})\n` +
          `**IMPORTANT** : Les identifiants candidats (candidateId) sont des identifiants techniques internes. Ne les mentionne JAMAIS dans tes réponses à l'utilisateur. Utilise uniquement le nom complet du candidat.\n\n` +
          contextCandidates
            .map((c: any) => {
              const name = [c.first_name, c.last_name].filter(Boolean).join(' ') || c.id;
              const partyNames = (c.party_ids ?? [])
                .map((pid: string) => partiesMap.get(pid)?.name ?? pid)
                .join(', ');
              const lines = [`## ${name}`];
              lines.push(`- candidateId (interne, ne pas afficher) : \`${c.id}\``);
              lines.push(`- **Parti(s)** : ${partyNames || 'Indépendant'}`);
              if (c.position) lines.push(`- **Position** : ${c.position}`);
              if (c.bio) lines.push(`- **Bio** : ${c.bio}`);
              if (c.website_url) lines.push(`- **Site web** : ${c.website_url}`);
              if (c.manifesto_pdf_url) lines.push(`- **Profession de foi / PDF programme** : ${c.manifesto_pdf_url}`);
              if (c.is_incumbent) lines.push(`- **Sortant** : oui`);
              if (c.birth_year) lines.push(`- **Année de naissance** : ${c.birth_year}`);
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

  // When candidateIds is empty (no candidates found for this municipality),
  // fall back to party manifesto search to avoid referencing unavailable tools
  const hasCandidates = candidateIds.length > 0;
  console.log('[ai-chat] routing:', { municipalityCode, hasCandidates, hasSelection, candidateCount: candidateIds.length, searchCandidateCount: searchCandidateIds.length, resolvedPartyIds });

  // Build human-readable candidate list for search instructions (name + internal ID for tool use)
  const searchCandidateLabels = searchCandidateIds.map((id) => {
    const name = candidateNamesMap.get(id.toLowerCase());
    return name ? `  - ${name} (candidateId: "${id}")` : `  - candidateId: "${id}"`;
  }).join('\n');

  const searchInstructions = municipalityCode && hasCandidates
    ? `# Protocole de recherche
**Obligation** : Appelle \`searchDocumentsWithRerank\` AVANT de rédiger ta réponse.
- L'outil effectue automatiquement des reformulations internes, du re-classement par pertinence PER-CANDIDAT, et une représentation équitable.
- Tu peux faire **plusieurs appels pour des THÉMATIQUES DIFFÉRENTES** (ex: transports + écologie). Mais ne répète PAS la même query — le cache retournera un résultat identique.
- Passe \`depth: "deep"\` pour une analyse détaillée ou un candidat unique, \`"shallow"\` (défaut) pour les comparaisons.
- Si un candidat n'a aucun résultat, mentionne-le explicitement dans ta réponse.
${hasSelection
  ? `- L'utilisateur a sélectionné ces candidats — recherche EXCLUSIVEMENT ceux-ci :
${searchCandidateLabels}

Appel recommandé :
\`searchDocumentsWithRerank({ query: "ta question", candidateIds: [${searchCandidateIds.map((id) => `"${id}"`).join(', ')}] })\``
  : `- Aucun candidat sélectionné — ne passe PAS de candidateIds pour rechercher dans TOUS les candidats.
- Présente les positions de TOUS les candidats de manière équitable.`}

## Règles
- Ne rédige ta réponse que quand tu as des résultats. Si la couverture est faible, relance avec une formulation différente.
- **Ne mentionne JAMAIS les identifiants techniques (candidateId, party_id) dans tes réponses.** Utilise uniquement les noms des candidats et des partis.
- Appelle \`suggestFollowUps\` à la fin de chaque réponse.`
    : `# Protocole de recherche
**Obligation** : Appelle \`searchDocumentsWithRerank\` avec les partis à rechercher AVANT de rédiger ta réponse.
- Tu peux faire **plusieurs appels pour des THÉMATIQUES DIFFÉRENTES**. Mais ne répète PAS la même query.
- Passe \`depth: "deep"\` pour une analyse détaillée d'un seul parti, \`"shallow"\` (défaut) pour les comparaisons.
- Si un parti n'a pas de résultats, reformule ta requête avec des synonymes avant de conclure.

Partis à rechercher :
${resolvedPartyIds.map((id) => `  - "${id}"`).join('\n') || '  (aucun parti trouvé)'}

Appel recommandé :
\`searchDocumentsWithRerank({ query: "ta question", partyIds: [${resolvedPartyIds.map((id) => `"${id}"`).join(', ')}] })\`

## Règles
- **Ne mentionne JAMAIS les identifiants techniques dans tes réponses.** Utilise uniquement les noms des partis.
- Appelle \`suggestFollowUps\` à la fin de chaque réponse.`;

  const selectedCandidateNames = searchCandidateIds
    .map((id) => candidateNamesMap.get(id.toLowerCase()) ?? id)
    .join(', ');
  const contextLine = municipalityCode
    ? `L'utilisateur consulte les candidats de la commune ${municipalityName ?? municipalityCode}. ${hasSelection ? `Candidats sélectionnés : ${selectedCandidateNames}` : 'Aucun candidat sélectionné — montre TOUS les candidats.'}`
    : `L'utilisateur a sélectionné ces partis : ${partiesList}`;

  const systemPrompt = `${searchInstructions}

# Rôle
Tu es l'assistant ChatVote — un outil d'information civique neutre pour les élections municipales françaises de 2026.
Ta mission : aider chaque citoyen à comprendre et comparer les propositions des candidats de sa commune, en se basant exclusivement sur leurs documents officiels (programmes, professions de foi, sites web de campagne, votes parlementaires).

# Contexte
Date : ${currentDate}
${contextLine}

# Principes fondamentaux
1. **Rigueur factuelle** : Chaque affirmation doit être traçable à une source documentaire. Cite systématiquement [N] après chaque fait, où N est le champ \`id\` du résultat. Les \`id\` sont déjà numérotés de manière **séquentielle et globale** à travers tous les appels d'outils — utilise-les directement. Exemple : si un outil retourne id:1,2,3 et un autre id:4,5,6, cite [1], [4], etc. Si aucune source ne couvre un sujet, dis-le clairement : "Aucun des candidats ne mentionne ce sujet dans les documents disponibles." N'invente jamais, ne déduis jamais au-delà de ce que les sources disent explicitement.
2. **Neutralité absolue** : Tu ne juges pas, tu ne recommandes pas, tu ne classes pas les candidats. Pas d'adjectifs valorisants ("ambitieux", "courageux") ni dépréciatifs. Présente les faits et laisse le citoyen se forger son opinion.
3. **Transparence sur les limites** : Si l'information est partielle, dis-le. Si un candidat n'a pas de position documentée sur un sujet, mentionne-le explicitement plutôt que de l'omettre silencieusement. Distingue "pas trouvé dans nos documents" de "le candidat n'en parle pas".

# Fiabilité des sources
Indique le niveau de fiabilité pour chaque type de source utilisée :
- 🥇 **FIABILITÉ maximale** : Sources gouvernementales (data.gouv.fr, résultats officiels)
- 🥈 **FIABILITÉ élevée** : Documents officiels des candidats (programmes, professions de foi, sites de campagne)
- 🥉 **FIABILITÉ modérée** : Informations vérifiables mais interprétatives (médias, presse)
- ⚠️ **NON VÉRIFIÉ** : Informations provenant du web (webSearch) — peuvent être inexactes ou partiales

Quand tu utilises des résultats de **webSearch**, ajoute un avertissement : "ℹ️ Ces informations proviennent du web et peuvent contenir des inexactitudes. Vérifiez auprès de sources officielles."

# Limite d'appels d'outils
Tu disposes d'un maximum de **${aiConfig.maxSearchCalls} appels de recherche** et **10 étapes au total** par réponse. Planifie tes recherches efficacement :
- Fais UN appel thématique large plutôt que plusieurs appels étroits
- Après tes recherches, tu DOIS : 1) rédiger ta réponse textuelle, 2) appeler suggestFollowUps
- **OBLIGATION ABSOLUE** : Tu DOIS toujours produire un résumé textuel complet, même si les résultats sont partiels. Une réponse vide ou tronquée est INACCEPTABLE.
- **Séquence obligatoire** : Recherche(s) → Réponse textuelle → suggestFollowUps. JAMAIS de recherche après avoir commencé à écrire ta réponse.

# Format de réponse
- **Comparatif par défaut** : Quand plusieurs candidats sont concernés, structure ta réponse candidat par candidat avec des puces ou un tableau comparatif.
- **Détaillé et concret** : 3-5 puces par candidat avec les propositions clés, les mesures précises et les chiffres quand disponibles. Développe chaque point pour donner une vision complète.
- **Citations obligatoires [N]** : CHAQUE fait ou proposition DOIT se terminer par une ou plusieurs citations [N] correspondant au champ \`id\` du résultat de recherche. Format exact : \`[1]\`, \`[2,3]\`. Exemple correct : "Propose 10 000 logements sociaux [3]." Exemple INCORRECT : "Propose 10 000 logements sociaux." (sans citation). Ne rédige JAMAIS une puce ou un paragraphe factuel sans au moins un [N]. Si aucune source ne couvre un point, ne l'inclus pas.
- **Markdown** : Utilise les titres, puces, **gras** pour les mots-clés. N'utilise PAS de séparateurs horizontaux (---). N'utilise PAS *italique*.
- **Proactivité** : Si la question est vague, fais un choix raisonnable et agis plutôt que de poser des questions. Maximum 1 question de clarification.

# Règles techniques
- **Requêtes de recherche** : Le paramètre "query" doit être THÉMATIQUE — décris le SUJET, pas le candidat. N'inclus JAMAIS de noms de candidats, de partis ou de nuances dans la query. L'outil recherche automatiquement dans TOUS les candidats en parallèle. Exemple CORRECT : "engagements sécurité transports écologie". Exemple INCORRECT : "Pierre BERNARD Rassemblement National programme engagements".
- **UN seul appel suffit pour TOUS les candidats** : searchDocumentsWithRerank recherche automatiquement dans le namespace de CHAQUE candidat séparément et retourne les meilleurs résultats per-candidat. Ne fais PAS un appel par candidat — un seul appel couvre tout.
- **Appels multiples UNIQUEMENT pour des THÉMATIQUES DIFFÉRENTES** : Tu peux appeler plusieurs fois si la question couvre des sujets distincts (ex: un appel "transports mobilité" + un appel "écologie environnement"). Mais **n'appelle PAS plusieurs fois pour le même sujet** — les résultats seront identiques (cache automatique).
- **Profondeur** : Passe \`depth: "deep"\` quand la question demande une analyse détaillée ou cible un seul candidat. Utilise \`depth: "shallow"\` (défaut) pour les comparaisons multi-candidats.
- **Ciblage par candidateId** : Passe un seul candidateId UNIQUEMENT quand l'utilisateur demande spécifiquement les positions d'UN candidat ("Que propose Dupont sur X ?"). Pour les comparaisons, ne passe PAS de candidateIds — l'outil cherche dans tous automatiquement.
- **Recherche approfondie** : Appelle runDeepResearch UNIQUEMENT quand l'utilisateur demande explicitement une analyse approfondie ou complète. Ne l'utilise PAS automatiquement après searchDocumentsWithRerank.
- **Suggestions de suivi** : À la fin de CHAQUE réponse, appelle l'outil suggestFollowUps avec 3 questions pertinentes. N'écris JAMAIS les suggestions dans le texte de ta réponse — utilise TOUJOURS l'outil pour que l'utilisateur puisse cliquer dessus.
- **Choix interactifs** : Quand tu veux proposer des options, appelle l'outil presentOptions avec un label (la question) et les options. N'écris PAS la question ni les options dans le texte — l'outil affiche tout sous forme de boutons cliquables. Termine ton texte AVANT l'appel, ne répète rien après.
- **Protection des données** : Ne demande jamais d'intentions de vote, d'opinions personnelles, ni de données personnelles.
${resolvedFeatures.includes('widgets') ? `
# Visualisation (renderWidget)
Quand tu disposes de données chiffrées comparables (scores, pourcentages, budgets, résultats électoraux, statistiques démographiques…), appelle **renderWidget** pour les afficher sous forme de graphique interactif.
- **bar** : comparaison entre candidats/partis/communes (le plus fréquent)
- **pie** : répartition/distribution (ex : répartition des voix)
- **line** : tendance temporelle (ex : évolution du budget)
- **radar** : comparaison multi-critères
Appelle renderWidget APRÈS avoir obtenu les données (via searchDataGouv, RAG, etc.), pas avant. Fournis des données réelles issues de tes recherches, jamais de données fictives ou simulées.` : ''}

${respondInLanguage}${candidateContext}`;

  // Model: resolved from aiConfig (primary → fallback if Scaleway key missing)
  const modelName = process.env.SCALEWAY_EMBED_API_KEY ? aiConfig.primaryModel : aiConfig.fallbackModel;
  if (!process.env.SCALEWAY_EMBED_API_KEY) {
    console.warn('[ai-chat] SCALEWAY_EMBED_API_KEY missing, falling back to', aiConfig.fallbackModel);
  }
  let model: LanguageModel;
  if (modelName === 'scaleway-qwen') {
    model = scalewayChat;
  } else if (modelName === 'gemini-2.0-flash') {
    model = google('gemini-2.0-flash');
  } else {
    // default: gemini-2.5-flash
    model = google('gemini-2.5-flash');
  }

  const result = streamText({
    model,
    system: systemPrompt,
    messages,
    stopWhen: [stepCountIs(10), hasToolCall('suggestFollowUps'), hasToolCall('presentOptions')],
    toolChoice: 'auto',
    providerOptions: {
      google: { thinkingConfig: { thinkingBudget: 0 } },
    },
    onError({ error }) {
      console.error('[ai-chat] streamText error:', error);
    },
    onStepFinish({ stepNumber, text, toolCalls, finishReason, usage, response }) {
      console.log('[ai-chat:step]', {
        chatId,
        stepNumber,
        textLen: text?.length ?? 0,
        textPreview: text?.slice(0, 100),
        toolCalls: toolCalls?.map((t) => t?.toolName),
        finishReason,
        usage,
        responseMessages: response?.messages?.length,
      });
    },
    async onFinish({ text, steps, usage }) {
      console.log('[ai-chat:finish]', {
        textLen: text?.length ?? 0,
        textPreview: text?.slice(0, 200),
        stepsCount: steps?.length,
        stepTexts: steps?.map((s, i) => `step${i}: textLen=${s.text?.length ?? 0} reasoning=${JSON.stringify((s as any).reasoning)?.slice(0, 80)} tools=${s.toolCalls?.map(t => t.toolName).join(',') || 'none'}`),
      });
      // In multi-step tool-calling flows, `text` may be empty.
      // Collect text from all steps as the final output.
      const outputText = text || steps?.map((s) => s.text).filter(Boolean).join('\n') || '';
      if (langfuse && langfuseTraceId && outputText) {
        langfuse.trace({ id: langfuseTraceId, output: outputText });
        await langfuse.flushAsync();
      }
      // Persist conversation to Firestore (fire-and-forget, never blocks the response)
      if (!chatId) return;
      try {
        const now = new Date().toISOString();
        const chatRef = db.collection('chat_sessions').doc(chatId);
        const doc = await chatRef.get();

        // Build a slim message pair from the latest exchange
        const lastUserMsg = uiMessages.filter((m) => m.role === 'user').at(-1);
        const newMessages = [
          ...(lastUserMsg ? [{ role: 'user' as const, content: lastUserMsg.parts?.map((p) => ('text' in p ? p.text : '')).join('') ?? '', timestamp: now }] : []),
          { role: 'assistant' as const, content: outputText, timestamp: now },
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
            mode: 'ai',
          });
        } else {
          // Create new conversation document
          await chatRef.set({
            messages: newMessages,
            municipality_code: municipalityCode ?? null,
            party_ids: resolvedPartyIds,
            locale: locale ?? 'fr',
            enabled_features: resolvedFeatures,
            created_at: now,
            updated_at: now,
            total_tokens: usage?.totalTokens ?? 0,
            mode: 'ai',
            user_id: uid ?? null,
          });
        }
      } catch (err) {
        console.error('[ai-chat] Failed to persist conversation:', err);
      }
    },
    tools: buildTools(resolvedFeatures, candidateIds, candidateNamesMap, searchCandidateIds, aiConfig),
  });

  return result.toUIMessageStreamResponse({
    originalMessages: uiMessages ?? [],
  });

  }); // end propagateAttributes
}, { name: 'ai-chat', endOnExit: false }); // end observe

export async function POST(req: Request) {
  const response = await handleChat(req);
  after(async () => {
    await Promise.all([
      langfuseSpanProcessor.forceFlush(),
      langfuse?.flushAsync(),
    ]);
  });
  return response;
}
