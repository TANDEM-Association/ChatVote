import { google } from '@ai-sdk/google';
import { type UIMessage, type LanguageModel, convertToModelMessages, stepCountIs, tool } from 'ai';
import { streamText } from '@lib/ai/tracing';
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

  return {
    // ── RAG search tools (feature-gated) ────────────────────────────────────
    ...(ragEnabled
      ? {
          searchPartyManifesto: tool({
            description:
              "Recherche dans le programme/manifeste PDF d'un parti politique. Contient les engagements officiels, propositions thématiques et priorités du parti. Appelle cet outil pour CHAQUE parti pertinent — les appels simultanés sont possibles et recommandés.",
            inputSchema: z.object({
              partyId: z.string().describe('Identifiant du parti (ex: "ps", "lr") — utilise les IDs fournis dans le contexte'),
              query: z.string().describe('Requête de recherche autonome et complète — pas de pronoms ni références implicites'),
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
            description: "Recherche dans TOUTES les sources d'un candidat : site officiel, profession de foi (PDF), documents de campagne uploadés, pages web scrapées. Utilise cet outil quand l'utilisateur pose une question sur un candidat précis. Pour une recherche globale sur toute la commune, préfère searchAllCandidates.",
            inputSchema: z.object({
              candidateId: z.string().describe('Identifiant du candidat — utilise les IDs fournis dans le contexte'),
              query: z.string().describe('Requête de recherche autonome et spécifique au candidat'),
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
                return { candidateId, candidateName: candidateNames.get(candidateId.toLowerCase()) ?? candidateId, results, count: results.length };
              } catch (err) {
                console.error('[ai-chat] searchCandidateWebsite error:', err);
                return { candidateId, candidateName: candidateNames.get(candidateId.toLowerCase()) ?? candidateId, results: [] as SearchResult[], count: 0, error: String(err) };
              }
            },
          }),
          // Search ALL candidates in the commune with multi-query support, each query re-ranked independently
          ...(candidateIds.length > 0
            ? {
                searchAllCandidates: tool({
                  description:
                    'Recherche simultanée dans TOUTES les sources de TOUS les candidats de la commune (sites web, professions de foi PDF, documents de campagne uploadés). Accepte plusieurs requêtes pour une couverture maximale — chaque requête est classée indépendamment puis fusionnée. Utilise cet outil pour toute question comparative ou générale. Stratégie optimale : 2-3 formulations variées couvrant synonymes et angles différents.',
                  inputSchema: z.object({
                    queries: z
                      .array(z.string())
                      .min(1)
                      .max(5)
                      .describe(
                        'Requêtes de recherche variées pour maximiser le rappel. Utilise 2-3 formulations différentes couvrant le même sujet (ex: ["transports en commun plan vélo", "mobilité urbaine piste cyclable", "stationnement voiture circulation"])',
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
              "Recherche dans les votes de l'Assemblée nationale. Contient les scrutins publics avec le détail par groupe parlementaire (pour, contre, abstention). Utilise pour vérifier la cohérence entre les promesses d'un parti et ses votes passés, ou pour illustrer une position avec des faits concrets.",
            inputSchema: z.object({
              query: z.string().describe('Sujet, loi ou projet de loi à rechercher (ex: "loi climat résilience", "réforme retraites 2023")'),
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
      description: "Lance une recherche approfondie multi-requêtes dans toutes les sources des candidats sélectionnés (sites web, professions de foi, documents uploadés). Utilise quand les premières recherches ne donnent pas assez de résultats, ou quand l'utilisateur demande une analyse approfondie. Le sous-agent reformule automatiquement avec synonymes et termes officiels.",
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
        return {
          findings: result.findings.slice(0, 12).map((r) => ({
            content: r.content.slice(0, 300),
            source: r.source,
            url: r.url,
            score: r.score,
            party_id: r.party_id,
            candidate_name: r.candidate_name,
          })),
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
  const candidateNamesMap = new Map<string, string>();
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

        // Build rich candidate context for system prompt
        // Note: candidate IDs are internal identifiers for tool calls only — never show them to the user
        candidateContext =
          `\n\n# Candidats disponibles dans cette commune (${municipalityCode})\n` +
          `**IMPORTANT** : Les identifiants candidats (candidateId) sont des identifiants techniques internes. Ne les mentionne JAMAIS dans tes réponses à l'utilisateur. Utilise uniquement le nom complet du candidat.\n\n` +
          candidates
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

  const iterativeSearchRules = `
## Stratégie de recherche itérative
Tu disposes de **12 tours d'outils maximum**. Utilise-les intelligemment :

**Tour 1 — Recherche initiale** : Lance tes premières recherches en parallèle (plusieurs appels simultanés).
**Tour 2 — Évaluation + approfondissement** : Examine les résultats. Si un candidat a 0 résultat ou si la couverture est faible :
  - Reformule avec des synonymes (ex : "écologie" → "environnement", "transition énergétique", "développement durable")
  - Essaie des termes plus spécifiques ou plus généraux
  - Appelle runDeepResearch si < 3 résultats au total
**Tour 3+ — Compléments ciblés** : Recherches additionnelles pour combler les trous identifiés.
**Dernier tour — Réponse** : Rédige ta réponse + appelle suggestFollowUps.

**Règles clés** :
- Lance TOUJOURS plusieurs recherches en parallèle au premier tour (pas une seule requête).
- Varie les formulations : synonymes, termes courants vs administratifs, angles différents.
- Après chaque tour, évalue : "Ai-je assez de matière pour chaque candidat concerné ?" Si non, relance.
- Ne rédige ta réponse que quand tu as suffisamment de données OU que tu as épuisé tes reformulations.
- **Ne mentionne JAMAIS les identifiants techniques (candidateId, party_id) dans tes réponses.** Utilise uniquement les noms des candidats et des partis.`;

  const searchInstructions = municipalityCode && hasCandidates
    ? hasSelection && searchCandidateIds.length <= 3
      ? `# Protocole de recherche
**Obligation** : Appelle searchCandidateWebsite pour CHAQUE candidat ci-dessous AVANT de rédiger ta réponse.
- En mode commune, n'utilise PAS searchPartyManifesto — les outils candidats (searchCandidateWebsite / searchAllCandidates) cherchent déjà dans toutes les sources : sites web, professions de foi PDF, documents de campagne.
- L'utilisateur a sélectionné ces candidats via le panneau latéral — recherche UNIQUEMENT ces candidats.
- Si un candidat n'a pas de résultats sur le sujet, reformule ta requête (synonymes, termes officiels). Si toujours rien, dis-le explicitement.

Candidats sélectionnés :
${searchCandidateLabels}
${iterativeSearchRules}`
      : hasSelection
        ? `# Protocole de recherche
**Obligation** : Appelle searchAllCandidates avec 2-3 formulations variées de la requête AVANT de rédiger ta réponse.
- searchAllCandidates recherche automatiquement dans les candidats sélectionnés et re-classe par pertinence.
- En mode commune, n'utilise PAS searchPartyManifesto — les outils candidats (searchCandidateWebsite / searchAllCandidates) cherchent déjà dans toutes les sources : sites web, professions de foi PDF, documents de campagne.
- L'utilisateur a sélectionné des candidats via le panneau latéral — concentre-toi EXCLUSIVEMENT sur eux.

Candidats sélectionnés (${searchCandidateIds.length}) :
${searchCandidateLabels}
${iterativeSearchRules}`
        : `# Protocole de recherche
**Obligation** : Appelle searchAllCandidates avec 2-3 formulations variées de la requête AVANT de rédiger ta réponse.
- searchAllCandidates recherche automatiquement dans TOUS les candidats et re-classe par pertinence.
- En mode commune, n'utilise PAS searchPartyManifesto — les outils candidats (searchCandidateWebsite / searchAllCandidates) cherchent déjà dans toutes les sources : sites web, professions de foi PDF, documents de campagne.
- Aucun candidat sélectionné — présente les positions de TOUS les candidats de la commune de manière équitable.
- Ne demande JAMAIS à l'utilisateur de préciser quel candidat — recherche dans tous et présente les résultats.
${iterativeSearchRules}`
    : `# Protocole de recherche
**Obligation** : Appelle searchPartyManifesto pour CHAQUE parti ci-dessous AVANT de rédiger ta réponse.
- Ne demande JAMAIS à l'utilisateur de préciser quel parti — recherche dans TOUS systématiquement.
- Si un parti n'a pas de résultats sur le sujet, reformule ta requête avec des synonymes avant de conclure.

Partis à rechercher (un appel searchPartyManifesto par parti) :
${resolvedPartyIds.map((id) => `  - partyId: "${id}"`).join('\n') || '  (aucun parti trouvé)'}
${iterativeSearchRules}`;

  const selectedCandidateNames = searchCandidateIds
    .map((id) => candidateNamesMap.get(id.toLowerCase()) ?? id)
    .join(', ');
  const contextLine = municipalityCode
    ? `L'utilisateur consulte les candidats de la commune ${municipalityCode}. ${hasSelection ? `Candidats sélectionnés : ${selectedCandidateNames}` : 'Aucun candidat sélectionné — montre TOUS les candidats.'}`
    : `L'utilisateur a sélectionné ces partis : ${partiesList}`;

  const systemPrompt = `${searchInstructions}

# Rôle
Tu es l'assistant ChatVote — un outil d'information civique neutre pour les élections municipales françaises de 2026.
Ta mission : aider chaque citoyen à comprendre et comparer les propositions des candidats de sa commune, en se basant exclusivement sur leurs documents officiels (programmes, professions de foi, sites web de campagne, votes parlementaires).

# Contexte
Date : ${currentDate}
${contextLine}

# Principes fondamentaux
1. **Rigueur factuelle** : Chaque affirmation doit être traçable à une source documentaire. Cite systématiquement [1], [2], etc. après chaque fait. Si aucune source ne couvre un sujet, dis-le clairement : "Aucun des candidats ne mentionne ce sujet dans les documents disponibles." N'invente jamais, ne déduis jamais au-delà de ce que les sources disent explicitement.
2. **Neutralité absolue** : Tu ne juges pas, tu ne recommandes pas, tu ne classes pas les candidats. Pas d'adjectifs valorisants ("ambitieux", "courageux") ni dépréciatifs. Présente les faits et laisse le citoyen se forger son opinion.
3. **Transparence sur les limites** : Si l'information est partielle, dis-le. Si un candidat n'a pas de position documentée sur un sujet, mentionne-le explicitement plutôt que de l'omettre silencieusement. Distingue "pas trouvé dans nos documents" de "le candidat n'en parle pas".

# Format de réponse
- **Comparatif par défaut** : Quand plusieurs candidats sont concernés, structure ta réponse candidat par candidat avec des puces ou un tableau comparatif.
- **Concis et concret** : 1-3 puces par candidat avec les propositions clés et les chiffres quand disponibles. Développe uniquement si l'utilisateur le demande.
- **Markdown** : Utilise les titres, puces, **gras** pour les mots-clés, et *italique* pour les informations non sourcées.
- **Proactivité** : Si la question est vague, fais un choix raisonnable et agis plutôt que de poser des questions. Maximum 1 question de clarification.

# Règles techniques
- **Requêtes de recherche** : Tes paramètres "query" doivent être AUTONOMES et COMPLETS. Jamais de pronoms ("ça", "ce sujet"), jamais de références implicites au contexte. Exemple : au lieu de "et sur ça ?", écris "propositions transports en commun et mobilité douce [nom commune]".
- **Recherche multi-requêtes** : Lance TOUJOURS plusieurs recherches en parallèle dès le premier tour. Utilise des formulations variées (synonymes, termes courants/officiels, angles différents). Évalue les résultats avant de rédiger — si la couverture est insuffisante, relance avec de nouvelles formulations.
- **Recherche approfondie** : Si après 2 tours tes résultats sont toujours insuffisants (< 3 résultats pertinents), appelle runDeepResearch. Utilise aussi cet outil quand l'utilisateur demande explicitement une analyse approfondie ou complète.
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
    stopWhen: stepCountIs(12),
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
    tools: buildTools(enabledFeatures, candidateIds, candidateNamesMap, searchCandidateIds),
  });

  return result.toUIMessageStreamResponse({
    originalMessages: uiMessages ?? [],
  });
}
