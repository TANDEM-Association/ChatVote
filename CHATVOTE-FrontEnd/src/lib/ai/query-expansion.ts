import { google } from '@ai-sdk/google';
import { generateObject } from 'ai';
import { observe } from '@langfuse/tracing';
import { z } from 'zod/v4';

// ── Schema ──────────────────────────────────────────────────────────────────

const expansionSchema = z.object({
  queries: z
    .array(z.string())
    .describe(
      'Requêtes de recherche vectorielle optimisées, variées et autonomes (2-3 requêtes)',
    ),
});

// ── Query expansion ─────────────────────────────────────────────────────────
// Mirrors the Python backend's generate_improvement_rag_query() step:
// Takes the user's raw question and generates 2-3 RAG-optimized search queries
// with synonyms, official terms, and different angles for better recall.

export const expandSearchQueries = observe(
  async function expandSearchQueries(
    userQuery: string,
    context?: {
      entityName?: string;
      entityType?: 'party' | 'candidate';
      conversationHint?: string;
    },
  ): Promise<string[]> {
    const start = Date.now();
    console.log(
      `[query-expansion] Starting for q="${userQuery.slice(0, 60)}"`,
    );

    const entityContext = context?.entityName
      ? `\nEntité cible : ${context.entityName} (${context.entityType === 'candidate' ? 'candidat' : 'parti politique'})`
      : '';

    try {
      const result = await generateObject({
        model: google('gemini-2.0-flash'),
        schema: expansionSchema,
        system: `Tu es un expert en recherche documentaire pour les élections françaises.
On te donne une question d'un citoyen. Génère 2-3 requêtes de recherche vectorielle OPTIMISÉES pour retrouver les passages pertinents dans des documents politiques (programmes, professions de foi, sites web de campagne, votes parlementaires).
${entityContext}

# Stratégies de reformulation
1. **Synonymes et termes officiels** : "écologie" → "transition écologique", "plan climat", "développement durable"
2. **Termes concrets vs abstraits** : "pouvoir d'achat" → "baisse TVA", "chèque énergie", "revalorisation salaires"
3. **Angles complémentaires** : "sécurité" → "police municipale effectifs", "vidéosurveillance caméras", "prévention délinquance"

# Règles
- Chaque requête doit être AUTONOME (pas de pronoms, pas de "ce sujet")
- Chaque requête doit couvrir un ANGLE DIFFÉRENT (pas juste des synonymes proches)
- Privilégie les termes que l'on trouve dans les documents officiels français
- 2 requêtes suffisent si le sujet est précis, 3 si le sujet est large
- Inclus toujours la requête originale (éventuellement nettoyée) comme première requête`,
        prompt: `Question du citoyen : "${userQuery}"

Génère les requêtes de recherche optimisées.`,
        abortSignal: AbortSignal.timeout(5000),
      });

      const queries = result.object.queries.slice(0, 3);
      console.log(
        `[query-expansion] Done: ${queries.length} queries in ${Date.now() - start}ms → ${queries.map((q) => `"${q.slice(0, 50)}"`).join(', ')}`,
      );
      return queries;
    } catch (err) {
      console.error(
        `[query-expansion] Failed (${Date.now() - start}ms), using original query:`,
        err,
      );
      // Fallback: return the original query
      return [userQuery];
    }
  },
  { name: 'query-expansion' },
);
