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


function buildTools(enabledFeatures: string[] | undefined, candidateIds: string[] = [], candidateNames: Map<string, string> = new Map(), selectedCandidateIds: string[] = []) {
  const features = enabledFeatures ?? ['rag'];
  const ragEnabled = features.includes('rag');

  // Global source counter — shared across ALL tool calls so each source gets a
  // unique sequential number (e.g. tool call 1 → [1-5], tool call 2 → [6-10]).
  // This lets the LLM cite [1], [2], [3]… reliably without renumbering.
  let globalSourceCounter = 0;



  /** Assign globally unique sequential IDs to search results */
  function assignGlobalIds<T>(results: T[]): (T & { id: number })[] {
    return results.map((r) => ({ ...r, id: ++globalSourceCounter }));
  }


  return {
    // ── RAG search tools (feature-gated) ────────────────────────────────────
    ...(ragEnabled
      ? {
          searchDocuments: tool({
            description:
              "Recherche unifiée dans tous les documents politiques : programmes de parti (PDF), sites web de candidats, professions de foi, documents de campagne. L'outil effectue automatiquement des reformulations internes et du re-classement par pertinence. **UN SEUL appel suffit** — passe tous les candidats/partis à rechercher en une fois. Ne rappelle JAMAIS cet outil avec les mêmes filtres.",
            inputSchema: z.object({
              query: z.string().describe('Requête de recherche autonome et complète — pas de pronoms ni références implicites'),
              candidateIds: z
                .array(z.string())
                .optional()
                .describe('Filtrer par candidats (IDs fournis dans le contexte). Si omis et partyIds omis, recherche tous les candidats de la commune.'),
              partyIds: z
                .array(z.string())
                .optional()
                .describe('Filtrer par partis (IDs fournis dans le contexte). Recherche dans les programmes/manifestes nationaux des partis.'),
            }),
            execute: async (input) => {
              const { query, candidateIds: filterCandidateIds, partyIds: filterPartyIds } = input;

              try {
                // Query expansion: generate 2-3 RAG-optimized variants
                const queries = await expandSearchQueries(query);
                if (process.env.NODE_ENV === 'development') {
                  console.log(`[searchDocuments] ${queries.length} expanded queries for "${query.slice(0, 60)}"`);
                }

                // Pre-embed all queries once
                const vectors = await Promise.all(queries.map((q) => embedQuery(q)));
                const queryVectors = new Map(queries.map((q, i) => [q, vectors[i]]));

                const allEntityResults: Array<SearchResult & { entityId: string; entityType: 'candidate' | 'party'; entityName: string }> = [];

                // ── Search candidate documents ──
                const searchCids = filterCandidateIds?.map((id) => id.toLowerCase())
                  ?? ((!filterPartyIds || filterPartyIds.length === 0)
                    ? (selectedCandidateIds.length > 0 ? selectedCandidateIds : candidateIds)
                    : []);
                if (process.env.NODE_ENV === 'development') {
                  console.log(`[searchDocuments] searchCids=${JSON.stringify(searchCids)} (${searchCids.length} entities)`);
                }

                if (searchCids.length > 0) {
                  const candidateResults = await Promise.all(
                    searchCids.map(async (cid) => {
                      const perQuery = await Promise.all(
                        queries.map(async (q) => {
                          const vec = queryVectors.get(q)!;
                          // Use 0.25 threshold — LLM reranking filters out irrelevant results later
                          return searchQdrant(
                            COLLECTIONS.candidatesWebsites, q, 'metadata.namespace', cid, 10, vec, { scoreThreshold: 0.25 },
                          );
                        }),
                      );
                      const deduped = deduplicateResults(perQuery.flat());
                      const name = candidateNames.get(cid) ?? cid;
                      return deduped.map((r) => ({ ...r, entityId: cid, entityType: 'candidate' as const, entityName: name }));
                    }),
                  );
                  allEntityResults.push(...candidateResults.flat());
                }

                // ── Search party manifesto documents ──
                const searchPids = filterPartyIds?.map((id) => id.toLowerCase()) ?? [];

                if (searchPids.length > 0) {
                  const partyResults = await Promise.all(
                    searchPids.map(async (pid) => {
                      const perQuery = await Promise.all(
                        queries.map((q) => searchQdrant(COLLECTIONS.allParties, q, 'metadata.namespace', pid, 10, undefined, { scoreThreshold: 0.25 })),
                      );
                      const deduped = deduplicateResults(perQuery.flat());
                      return deduped.map((r) => ({ ...r, entityId: pid, entityType: 'party' as const, entityName: pid }));
                    }),
                  );
                  allEntityResults.push(...partyResults.flat());
                }

                if (allEntityResults.length === 0) {
                  return { results: [] as SearchResult[], count: 0, message: 'Aucun document trouvé pour ces filtres.' };
                }

                // ── Per-entity reranking for fair representation ──
                const byEntityMap = new Map<string, typeof allEntityResults>();
                for (const r of allEntityResults) {
                  if (!byEntityMap.has(r.entityId)) byEntityMap.set(r.entityId, []);
                  byEntityMap.get(r.entityId)!.push(r);
                }

                const entityGroups = Array.from(byEntityMap.entries());
                const perEntityTopK = Math.max(3, Math.ceil(16 / Math.max(entityGroups.length, 1)));

                const perEntityReranked = await Promise.all(
                  entityGroups.map(async ([entityId, results]) => {
                    const sorted = results.sort((a, b) => (b.score ?? 0) - (a.score ?? 0)).slice(0, 10);
                    const top = sorted.length <= perEntityTopK
                      ? sorted
                      : await rerankResults(sorted, query, perEntityTopK);
                    return top.map((r) => ({ ...r, entityId, entityName: results[0].entityName, entityType: results[0].entityType }));
                  }),
                );

                // Round-robin interleave for fair representation
                const interleaved: typeof allEntityResults = [];
                const maxLen = Math.max(...perEntityReranked.map((g) => g.length));
                for (let i = 0; i < maxLen && interleaved.length < 16; i++) {
                  for (const group of perEntityReranked) {
                    if (i < group.length && interleaved.length < 16) {
                      interleaved.push(group[i]);
                    }
                  }
                }

                const reranked = assignGlobalIds(interleaved);
                const entitiesWithResults = new Set(reranked.map((r: any) => r.entityId));

                if (process.env.NODE_ENV === 'development') {
                  console.log(`[searchDocuments] Done: ${allEntityResults.length} raw → ${reranked.length} final across ${entitiesWithResults.size} entities`);
                }

                return {
                  results: reranked,
                  count: reranked.length,
                  entitiesSearched: entityGroups.length,
                  entitiesWithResults: entitiesWithResults.size,
                };
              } catch (err) {
                console.error('[ai-chat] searchDocuments error:', err);
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
      description: "Recherche approfondie multi-sources. **N'utilise cet outil QUE si l'utilisateur demande EXPLICITEMENT une analyse approfondie** (ex: 'analyse en profondeur', 'recherche complète'). Pour les questions normales, searchDocuments suffit — il gère déjà la reformulation et le re-classement.",
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
        "Change la commune de l'utilisateur. Utilise quand l'utilisateur mentionne une autre ville ou demande à changer de commune. Déclenche le rechargement des candidats disponibles dans la nouvelle commune.",
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

        return {
          action: 'changeCity',
          cityName: input.cityName,
          municipalityCode: code,
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

const handleChat = observe(async function handleChat(req: Request) {
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
**Obligation** : Appelle \`searchDocuments\` AVANT de rédiger ta réponse.
- UN SEUL appel suffit — passe tous les candidats à rechercher dans le champ \`candidateIds\`.
- L'outil effectue automatiquement des reformulations internes, du re-classement par pertinence, et une représentation équitable de chaque candidat.
- **N'appelle JAMAIS searchDocuments deux fois avec les mêmes candidateIds.** Si les résultats sont insuffisants, relance avec une query RADICALEMENT différente.
- Si un candidat n'a aucun résultat, mentionne-le explicitement dans ta réponse.
${hasSelection
  ? `- L'utilisateur a sélectionné ces candidats — recherche EXCLUSIVEMENT ceux-ci :
${searchCandidateLabels}

Appel recommandé :
\`searchDocuments({ query: "ta question", candidateIds: [${searchCandidateIds.map((id) => `"${id}"`).join(', ')}] })\``
  : `- Aucun candidat sélectionné — ne passe PAS de candidateIds pour rechercher dans TOUS les candidats.
- Présente les positions de TOUS les candidats de manière équitable.`}

## Règles
- Ne rédige ta réponse que quand tu as des résultats. Si la couverture est faible, relance avec une formulation différente.
- **Ne mentionne JAMAIS les identifiants techniques (candidateId, party_id) dans tes réponses.** Utilise uniquement les noms des candidats et des partis.
- Appelle \`suggestFollowUps\` à la fin de chaque réponse.`
    : `# Protocole de recherche
**Obligation** : Appelle \`searchDocuments\` avec les partis à rechercher AVANT de rédiger ta réponse.
- UN SEUL appel suffit — passe tous les partis dans le champ \`partyIds\`.
- Si un parti n'a pas de résultats, reformule ta requête avec des synonymes avant de conclure.

Partis à rechercher :
${resolvedPartyIds.map((id) => `  - "${id}"`).join('\n') || '  (aucun parti trouvé)'}

Appel recommandé :
\`searchDocuments({ query: "ta question", partyIds: [${resolvedPartyIds.map((id) => `"${id}"`).join(', ')}] })\`

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

# Format de réponse
- **Comparatif par défaut** : Quand plusieurs candidats sont concernés, structure ta réponse candidat par candidat avec des puces ou un tableau comparatif.
- **Concis et concret** : 1-3 puces par candidat avec les propositions clés et les chiffres quand disponibles. Développe uniquement si l'utilisateur le demande.
- **Markdown** : Utilise les titres, puces, **gras** pour les mots-clés, et *italique* pour les informations non sourcées.
- **Proactivité** : Si la question est vague, fais un choix raisonnable et agis plutôt que de poser des questions. Maximum 1 question de clarification.

# Règles techniques
- **Requêtes de recherche** : Tes paramètres "query" doivent être AUTONOMES et COMPLETS. Jamais de pronoms ("ça", "ce sujet"), jamais de références implicites au contexte. Exemple : au lieu de "et sur ça ?", écris "propositions transports en commun et mobilité douce [nom commune]".
- **UN SEUL appel searchDocuments suffit** : L'outil effectue automatiquement la reformulation en 2-3 requêtes variées, la recherche parallèle, et le re-classement par pertinence. **N'appelle PAS searchDocuments plusieurs fois** — les résultats seront identiques. Rédige ta réponse directement après le premier appel.
- **Recherche approfondie** : Appelle runDeepResearch UNIQUEMENT quand l'utilisateur demande explicitement une analyse approfondie ou complète. Ne l'utilise PAS automatiquement après searchDocuments.
- **Suggestions de suivi** : À la fin de CHAQUE réponse, appelle l'outil suggestFollowUps avec 3 questions pertinentes. N'écris JAMAIS les suggestions dans le texte de ta réponse — utilise TOUJOURS l'outil pour que l'utilisateur puisse cliquer dessus.
- **Choix interactifs** : Quand tu veux proposer des options, appelle l'outil presentOptions avec un label (la question) et les options. N'écris PAS la question ni les options dans le texte — l'outil affiche tout sous forme de boutons cliquables. Termine ton texte AVANT l'appel, ne répète rien après.
- **Protection des données** : Ne demande jamais d'intentions de vote, d'opinions personnelles, ni de données personnelles.
${(enabledFeatures ?? []).includes('widgets') ? `
# Visualisation (renderWidget)
Quand tu disposes de données chiffrées comparables (scores, pourcentages, budgets, résultats électoraux, statistiques démographiques…), appelle **renderWidget** pour les afficher sous forme de graphique interactif.
- **bar** : comparaison entre candidats/partis/communes (le plus fréquent)
- **pie** : répartition/distribution (ex : répartition des voix)
- **line** : tendance temporelle (ex : évolution du budget)
- **radar** : comparaison multi-critères
Appelle renderWidget APRÈS avoir obtenu les données (via searchDataGouv, RAG, etc.), pas avant. Fournis des données réelles issues de tes recherches, jamais de données fictives ou simulées.` : ''}

${respondInLanguage}${candidateContext}`;

  // Model: Scaleway Qwen3 235B (primary) → Gemini 2.5 Flash (fallback)
  let model: LanguageModel = scalewayChat;
  if (!process.env.SCALEWAY_EMBED_API_KEY) {
    console.warn('[ai-chat] SCALEWAY_EMBED_API_KEY missing, falling back to Gemini');
    model = google('gemini-2.5-flash');
  }

  const result = streamText({
    model,
    system: systemPrompt,
    messages,
    stopWhen: [stepCountIs(8), hasToolCall('suggestFollowUps'), hasToolCall('presentOptions')],
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
            enabled_features: enabledFeatures ?? [],
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
    tools: buildTools(enabledFeatures, candidateIds, candidateNamesMap, searchCandidateIds),
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
