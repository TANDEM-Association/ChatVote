import { google } from '@ai-sdk/google';
import { generateText, stepCountIs, tool } from 'ai';
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
      prompt: `Find relevant information for this query that returned insufficient results: "${originalQuery}"`,
      system: `You are a research assistant. Given a query that returned insufficient results from a vector database, your job is to find relevant information by:
1. Generating 2-3 alternative phrasings of the original query (synonyms, related terms, broader/narrower scope)
2. Searching across the provided collections with these alternative queries
3. Lowering the score threshold if initial searches return few results
4. Compiling all findings

Available collections: ${collections.join(', ')}
${candidateIds?.length ? `Candidate IDs for scoped search: ${candidateIds.join(', ')}` : ''}
${partyIds?.length ? `Party IDs for scoped search: ${partyIds.join(', ')}` : ''}

Original query that returned insufficient results: "${originalQuery}"

Search strategically: try different phrasings, try broader terms, try related concepts. When you have gathered enough results (or exhausted your search budget), call compileResults.`,
      stopWhen: stepCountIs(3),
      abortSignal: AbortSignal.timeout(25000),
      tools: {
        searchCollection: tool({
          description: 'Search a Qdrant collection for relevant content. Use different queries and thresholds to find more results.',
          inputSchema: z.object({
            collection: z.enum(COLLECTION_NAMES as [string, ...string[]]).describe('Collection to search'),
            query: z.string().describe('Search query — use varied phrasings for better recall'),
            namespace: z.string().optional().describe('Optional namespace filter (party_id or candidate_id)'),
            scoreThreshold: z.number().min(0.2).max(0.5).default(0.3).describe('Score threshold (lower = more results, less precise)'),
            limit: z.number().min(1).max(15).default(8).describe('Max results to return'),
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
          description: 'Compile all research findings. Call this when you have gathered enough results or exhausted your search budget.',
          inputSchema: z.object({
            summary: z.string().describe('Brief summary of what was found and what was tried'),
            queriesTried: z.array(z.string()).describe('All query variations that were attempted'),
            collectionsSearched: z.array(z.string()).describe('All collections that were searched'),
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
