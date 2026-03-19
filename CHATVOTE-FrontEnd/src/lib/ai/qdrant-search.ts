import { embedQuery } from './embedding';
import { qdrantClient } from './qdrant-client';
import { getLangfuse } from './tracing';

// ── Types ────────────────────────────────────────────────────────────────────

export interface QdrantPayload {
  page_content?: string;
  metadata?: {
    source?: string;
    url?: string;
    page?: number | string;
    party_id?: string;
    namespace?: string;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface SearchResult {
  id: number;
  score?: number;
  content: string;
  source: string;
  url: string;
  page: number | string;
  party_id: string;
  candidate_name: string;
  document_name: string;
  source_document: string;
}

// ── Options ──────────────────────────────────────────────────────────────────

interface SearchOptions {
  scoreThreshold?: number;
  /** Override the default must_not filter. Pass `null` to disable. */
  mustNot?: object[] | null;
  /** Langfuse trace ID — when provided, spans nest under this parent trace. */
  traceId?: string;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function mapResults(results: Array<{ payload?: Record<string, unknown> | null; score?: number }>): SearchResult[] {
  return results.map((r, idx) => {
    const payload = (r.payload ?? {}) as QdrantPayload;
    const meta = payload.metadata ?? {};

    let url = String(meta.url ?? '');
    if (url && !url.startsWith('http')) {
      url = '';
    }

    return {
      id: idx + 1,
      score: r.score ?? 0,
      content: String(payload.page_content ?? ''),
      source: String(meta.source ?? ''),
      url,
      page: (meta.page as number | string) ?? '',
      party_id: String(meta.party_id ?? meta.namespace ?? ''),
      candidate_name: String(meta.candidate_name ?? ''),
      document_name: String(meta.document_name ?? ''),
      source_document: String(meta.source_document ?? ''),
    };
  });
}

const DEFAULT_MUST_NOT = [{ key: 'metadata.fiabilite', range: { gt: 3 } }];

// ── Scoped search (with namespace filter) ────────────────────────────────────

export async function searchQdrant(
  collection: string,
  query: string,
  filterKey: string,
  filterValue: string,
  limit: number,
  precomputedVector?: number[],
  options?: SearchOptions,
): Promise<SearchResult[]> {
  const scoreThreshold = options?.scoreThreshold ?? 0.35;
  const mustNot = options?.mustNot === null ? undefined : (options?.mustNot ?? DEFAULT_MUST_NOT);

  const start = Date.now();
  console.log(`[ai-chat:qdrant] searching collection=${collection} ${filterKey}=${filterValue} limit=${limit} threshold=${scoreThreshold} q="${query.slice(0, 60)}"`);

  const langfuse = getLangfuse();
  const traceId = options?.traceId;
  const span = langfuse?.span({ name: 'qdrant-search', ...(traceId ? { traceId } : {}), input: { collection, query: query.slice(0, 200), filterKey, filterValue } });

  const embedding = precomputedVector ?? (await embedQuery(query));

  let results;
  try {
    results = await qdrantClient.search(collection, {
      vector: { name: 'dense', vector: embedding },
      filter: {
        must: [{ key: filterKey, match: { value: filterValue } }],
        ...(mustNot ? { must_not: mustNot } : {}),
      },
      score_threshold: scoreThreshold,
      limit,
      with_payload: true,
    });
  } catch (err) {
    console.error(`[ai-chat:qdrant] FAILED collection=${collection} ${filterKey}=${filterValue} ${Date.now() - start}ms`, err);
    span?.end({ output: { error: String(err) } });
    throw err;
  }

  console.log(`[ai-chat:qdrant] OK collection=${collection} ${filterKey}=${filterValue} results=${results.length} ${Date.now() - start}ms`);
  const mapped = mapResults(results);
  span?.end({ output: { resultCount: mapped.length, topScore: mapped[0]?.score } });
  return mapped;
}

// ── Broad search (no namespace filter) ───────────────────────────────────────

export async function searchQdrantBroad(
  collection: string,
  query: string,
  limit: number,
  precomputedVector?: number[],
  options?: SearchOptions,
): Promise<SearchResult[]> {
  const scoreThreshold = options?.scoreThreshold ?? 0.25;
  const mustNot = options?.mustNot === null ? undefined : (options?.mustNot ?? DEFAULT_MUST_NOT);

  const start = Date.now();
  console.log(`[ai-chat:qdrant] broad-searching collection=${collection} limit=${limit} threshold=${scoreThreshold} q="${query.slice(0, 60)}"`);

  const langfuse = getLangfuse();
  const traceId = options?.traceId;
  const span = langfuse?.span({ name: 'qdrant-search-broad', ...(traceId ? { traceId } : {}), input: { collection, query: query.slice(0, 200) } });

  const embedding = precomputedVector ?? (await embedQuery(query));

  let results;
  try {
    results = await qdrantClient.search(collection, {
      vector: { name: 'dense', vector: embedding },
      ...(mustNot ? { filter: { must_not: mustNot } } : {}),
      score_threshold: scoreThreshold,
      limit,
      with_payload: true,
    });
  } catch (err) {
    console.error(`[ai-chat:qdrant] broad FAILED collection=${collection} ${Date.now() - start}ms`, err);
    span?.end({ output: { error: String(err) } });
    throw err;
  }

  console.log(`[ai-chat:qdrant] broad OK collection=${collection} results=${results.length} ${Date.now() - start}ms`);
  const mapped = mapResults(results);
  span?.end({ output: { resultCount: mapped.length, topScore: mapped[0]?.score } });
  return mapped;
}

// ── Filterless search (with optional custom filter) ──────────────────────────
// Used by parliamentary questions which have an optional filter and no must_not

export async function searchQdrantRaw(
  collection: string,
  query: string,
  limit: number,
  options?: {
    scoreThreshold?: number;
    filter?: object;
    /** Langfuse trace ID — when provided, spans nest under this parent trace. */
    traceId?: string;
  },
): Promise<SearchResult[]> {
  const scoreThreshold = options?.scoreThreshold ?? 0.35;

  const start = Date.now();
  console.log(`[ai-chat:qdrant] raw-searching collection=${collection} limit=${limit} threshold=${scoreThreshold} q="${query.slice(0, 60)}"`);

  const langfuse = getLangfuse();
  const traceId = options?.traceId;
  const span = langfuse?.span({ name: 'qdrant-search-raw', ...(traceId ? { traceId } : {}), input: { collection, query: query.slice(0, 200) } });

  const embedding = await embedQuery(query);

  let results;
  try {
    results = await qdrantClient.search(collection, {
      vector: { name: 'dense', vector: embedding },
      ...(options?.filter ? { filter: options.filter } : {}),
      score_threshold: scoreThreshold,
      limit,
      with_payload: true,
    });
  } catch (err) {
    console.error(`[ai-chat:qdrant] raw FAILED collection=${collection} ${Date.now() - start}ms`, err);
    span?.end({ output: { error: String(err) } });
    throw err;
  }

  console.log(`[ai-chat:qdrant] raw OK collection=${collection} results=${results.length} ${Date.now() - start}ms`);
  const mapped = mapResults(results);
  span?.end({ output: { resultCount: mapped.length, topScore: mapped[0]?.score } });
  return mapped;
}

// ── Deduplication helper ─────────────────────────────────────────────────────

export function deduplicateResults(results: SearchResult[]): SearchResult[] {
  const seen = new Set<string>();
  return results.filter((r) => {
    const key = r.content.slice(0, 200);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).map((r, idx) => ({ ...r, id: idx + 1 }));
}
