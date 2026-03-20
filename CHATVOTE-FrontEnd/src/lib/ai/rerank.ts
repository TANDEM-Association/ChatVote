import { google } from '@ai-sdk/google';
import { generateObject } from 'ai';
import { observe } from '@langfuse/tracing';
import { z } from 'zod/v4';

import type { SearchResult } from './qdrant-search';

// ── Schema ──────────────────────────────────────────────────────────────────

const rerankSchema = z.object({
  indices: z
    .array(z.number())
    .describe(
      'Indices des documents les plus pertinents, ordonnés par pertinence décroissante (le plus pertinent en premier)',
    ),
});

// ── LLM-based reranking ─────────────────────────────────────────────────────
// Mirrors the Python backend's rerank_documents() step:
// Takes N Qdrant results and uses a fast LLM to pick the top-K most relevant
// for the user's actual question (vector similarity ≠ relevance).

export const rerankResults = observe(
  async function rerankResults(
    results: SearchResult[],
    query: string,
    topK: number = 5,
  ): Promise<SearchResult[]> {
    if (results.length <= topK) return results;

    const start = Date.now();
    console.log(
      `[rerank] Starting: ${results.length} results → top ${topK} for q="${query.slice(0, 60)}"`,
    );

    // Build compact document representations for the LLM
    const docsContext = results
      .map((r, i) => {
        const meta = [
          r.source && `source: ${r.source}`,
          r.candidate_name && `candidat: ${r.candidate_name}`,
          r.party_id && `parti: ${r.party_id}`,
          r.score != null && `score: ${r.score.toFixed(3)}`,
        ]
          .filter(Boolean)
          .join(' | ');
        return `[${i}] ${meta}\n${r.content.slice(0, 1000)}`;
      })
      .join('\n---\n');

    try {
      const result = await generateObject({
        model: google('gemini-2.5-flash'),
        schema: rerankSchema,
        experimental_telemetry: { isEnabled: true },
        system: `Tu es un expert en pertinence documentaire pour les élections françaises.

On te donne ${results.length} extraits de documents (programmes, professions de foi, sites de campagne, votes parlementaires).
Classe-les par pertinence par rapport à la question de l'utilisateur.

Critères de pertinence (par ordre d'importance) :
1. **Correspondance thématique directe** — le document traite exactement du sujet demandé
2. **Spécificité** — propositions concrètes, mesures chiffrées, engagements précis > déclarations vagues
3. **Diversité des candidats** — à pertinence égale, favorise la représentation de candidats différents
4. **Fraîcheur** — informations récentes > anciennes

Retourne les indices des ${topK} documents les plus pertinents, du plus au moins pertinent.

Documents :
${docsContext}`,
        prompt: `Question de l'utilisateur : "${query}"

Retourne les ${topK} indices les plus pertinents.`,
        abortSignal: AbortSignal.timeout(8000),
      });
      const { object } = result;

      // Extract valid indices
      const validIndices = object.indices.filter(
        (i) => i >= 0 && i < results.length,
      );
      const reranked = validIndices.slice(0, topK).map((i) => results[i]);

      // Pad with highest-scoring originals if reranking returned too few
      if (reranked.length < topK) {
        const usedIndices = new Set(validIndices.slice(0, topK));
        for (let i = 0; i < results.length && reranked.length < topK; i++) {
          if (!usedIndices.has(i)) reranked.push(results[i]);
        }
      }

      console.log(
        `[rerank] Done: ${results.length} → ${reranked.length} in ${Date.now() - start}ms`,
      );
      return reranked.map((r, idx) => ({ ...r, id: idx + 1 }));
    } catch (err) {
      console.error(
        `[rerank] Failed (${Date.now() - start}ms), returning score-sorted results:`,
        err,
      );
      return results.slice(0, topK).map((r, idx) => ({ ...r, id: idx + 1 }));
    }
  },
  { name: 'rerank-results' },
);
