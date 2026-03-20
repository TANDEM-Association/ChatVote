import { google } from '@ai-sdk/google';
import { stepCountIs, tool } from 'ai';
import { generateText } from './tracing';
import { z } from 'zod/v4';

import { COLLECTIONS } from './qdrant-client';
import { searchQdrant, searchQdrantBroad, deduplicateResults, type SearchResult } from './qdrant-search';

// ── Types ────────────────────────────────────────────────────────────────────

export interface DeepResearchResult {
  findings: SearchResult[];
  summary: string;
  queriesTried: string[];
  collectionsSearched: string[];
}

// ── Deep Research Sub-Agent ──────────────────────────────────────────────────

const COLLECTION_NAMES = Object.values(COLLECTIONS);

export async function deepResearch(params: {
  originalQuery: string;
  collections: string[];
  candidateIds?: string[];
  partyIds?: string[];
}): Promise<DeepResearchResult> {
  const { originalQuery, collections, candidateIds, partyIds } = params;
  const start = Date.now();

  console.log(`[deep-research] Starting for q="${originalQuery.slice(0, 80)}" collections=[${collections.join(',')}]`);

  // Budget counter for Qdrant calls
  let qdrantCallCount = 0;
  const QDRANT_BUDGET = 15;

  // Accumulate all findings across sub-agent steps
  const allFindings: SearchResult[] = [];
  const queriesTried: string[] = [];
  const collectionsSearched = new Set<string>();

  try {
    await generateText({
      model: google('gemini-2.5-flash'),
      providerOptions: {
        google: { thinkingConfig: { thinkingBudget: 0 } },
      },
      prompt: `Recherche approfondie pour : "${originalQuery}"`,
      system: `Tu es un agent de recherche documentaire spécialisé dans les données politiques françaises (programmes électoraux, professions de foi, sites de campagne, votes parlementaires, questions au gouvernement).

Ta mission : trouver un maximum d'informations pertinentes sur un sujet qui a retourné peu de résultats lors d'une première recherche vectorielle.

# Stratégie de recherche
1. **Reformulation** : Génère 2-3 variantes de la requête originale en exploitant synonymes, termes officiels, et angles différents. Ex: "écologie" → "transition énergétique", "plan climat", "développement durable".
2. **Élargissement progressif** : Commence par les collections ciblées, puis élargis. Baisse le seuil de score (scoreThreshold) si les premiers résultats sont insuffisants (0.35 → 0.30 → 0.25).
3. **Recherche par namespace** : Si des candidateIds ou partyIds sont fournis, cherche d'abord dans leur namespace spécifique, puis sans namespace pour rattraper les documents mal catégorisés.
4. **Arrêt intelligent** : Quand tu as ≥8 résultats pertinents OU que tu as épuisé tes variations, appelle compileResults.

# Contexte
Collections disponibles : ${collections.join(', ')}
${candidateIds?.length ? `IDs candidats (namespace) : ${candidateIds.join(', ')}` : 'Pas de filtre candidat — recherche large.'}
${partyIds?.length ? `IDs partis (namespace) : ${partyIds.join(', ')}` : ''}

Requête originale : "${originalQuery}"

Sois méthodique : varie les formulations, essaie les termes en français courant ET administratif, et compile tes résultats dès que tu as assez de matière.`,
      stopWhen: stepCountIs(3),
      abortSignal: AbortSignal.timeout(25000),
      tools: {
        searchCollection: tool({
          description: 'Recherche vectorielle dans une collection Qdrant. Varie les requêtes (synonymes, termes officiels/courants) et ajuste le seuil de score pour maximiser le rappel.',
          inputSchema: z.object({
            collection: z.enum(COLLECTION_NAMES as [string, ...string[]]).describe('Collection cible (programmes, sites candidats, votes, questions parlementaires)'),
            query: z.string().describe('Requête de recherche — utilise des formulations variées à chaque appel'),
            namespace: z.string().optional().describe('Filtre namespace optionnel (party_id ou candidate_id) — omets pour une recherche large'),
            scoreThreshold: z.number().min(0.2).max(0.5).default(0.3).describe('Seuil de pertinence (0.2 = large, 0.5 = strict) — baisse progressivement si peu de résultats'),
            limit: z.number().min(1).max(15).default(8).describe('Nombre max de résultats'),
          }),
          execute: async (input) => {
            if (qdrantCallCount >= QDRANT_BUDGET) {
              console.log(`[deep-research:budget] Budget exhausted (${qdrantCallCount}/${QDRANT_BUDGET})`);
              return { results: [], count: 0, error: 'Qdrant call budget exhausted' };
            }
            qdrantCallCount++;

            const { collection, query, namespace, scoreThreshold, limit } = input;
            console.log(`[deep-research:step] call=${qdrantCallCount}/${QDRANT_BUDGET} collection=${collection} ns=${namespace ?? 'broad'} threshold=${scoreThreshold} q="${query.slice(0, 60)}"`);

            queriesTried.push(query);
            collectionsSearched.add(collection);

            try {
              let results: SearchResult[];
              if (namespace) {
                results = await searchQdrant(
                  collection, query, 'metadata.namespace', namespace, limit,
                  undefined, { scoreThreshold },
                );
              } else {
                results = await searchQdrantBroad(
                  collection, query, limit,
                  undefined, { scoreThreshold },
                );
              }

              allFindings.push(...results);
              return { results: results.slice(0, 5).map(r => ({ content: r.content.slice(0, 200), source: r.source, url: r.url, score: r.score })), count: results.length };
            } catch (err) {
              console.error(`[deep-research:step] search failed:`, err);
              return { results: [], count: 0, error: String(err) };
            }
          },
        }),
        compileResults: tool({
          description: 'Compile les résultats de recherche. Appelle quand tu as ≥8 résultats pertinents OU que tu as épuisé tes variations de requêtes.',
          inputSchema: z.object({
            summary: z.string().describe('Bilan concis : ce qui a été trouvé, ce qui manque, et les pistes essayées'),
            queriesTried: z.array(z.string()).describe('Toutes les variantes de requêtes testées'),
            collectionsSearched: z.array(z.string()).describe('Toutes les collections consultées'),
          }),
          execute: async (input) => {
            return {
              compiled: true,
              summary: input.summary,
              totalFindings: allFindings.length,
            };
          },
        }),
      },
    });

    const elapsed = Date.now() - start;
    const deduplicated = deduplicateResults(allFindings);
    console.log(`[deep-research:done] findings=${deduplicated.length} queries=${queriesTried.length} qdrantCalls=${qdrantCallCount} ${elapsed}ms`);

    return {
      findings: deduplicated,
      summary: `Deep research completed in ${elapsed}ms. ${deduplicated.length} unique results from ${qdrantCallCount} Qdrant calls.`,
      queriesTried: [...new Set(queriesTried)],
      collectionsSearched: [...collectionsSearched],
    };
  } catch (err) {
    const elapsed = Date.now() - start;
    const isTimeout = err instanceof Error && (err.name === 'AbortError' || err.message.includes('abort'));
    console.warn(`[deep-research:${isTimeout ? 'timeout' : 'error'}] ${elapsed}ms`, err);

    // Return whatever we found so far (never worse than empty)
    const deduplicated = deduplicateResults(allFindings);
    return {
      findings: deduplicated,
      summary: isTimeout
        ? `Research timed out after ${elapsed}ms. Returning ${deduplicated.length} partial results.`
        : `Research failed: ${String(err)}. Returning ${deduplicated.length} partial results.`,
      queriesTried: [...new Set(queriesTried)],
      collectionsSearched: [...collectionsSearched],
    };
  }
}
