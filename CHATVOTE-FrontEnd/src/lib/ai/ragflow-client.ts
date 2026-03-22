/**
 * RAGFlow REST API client (v0.24.0)
 *
 * Env vars:
 *   RAGFLOW_API_URL  — base URL (default: http://localhost:9380)
 *   RAGFLOW_API_KEY  — Bearer token (generated in RAGFlow UI → Settings → API Keys)
 */

// Read env lazily so scripts that load .env after import still work
function getUrl() { return process.env.RAGFLOW_API_URL ?? 'http://localhost:8680'; }
function getKey() { return process.env.RAGFLOW_API_KEY; }
const TIMEOUT_MS = 10_000;

// ── Types ────────────────────────────────────────────────────────────────────

export interface RagflowChunk {
  content: string;
  document_name: string;
  dataset_name: string;
  similarity_score: number;
  metadata: Record<string, unknown>;
}

export interface RagflowDataset {
  id: string;
  name: string;
  chunk_method: string;
  language: string;
  document_count: number;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function headers(): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${getKey()}`,
  };
}

function checkKey(): boolean {
  if (!getKey()) {
    console.warn('[ragflow] RAGFLOW_API_KEY not set — skipping RAGFlow call');
    return false;
  }
  return true;
}

// ── Search ───────────────────────────────────────────────────────────────────

export async function searchRagflow(
  query: string,
  datasetIds?: string[],
  topK = 6,
  similarityThreshold = 0.2,
  useKg = false,
): Promise<RagflowChunk[]> {
  if (!checkKey()) return [];

  const body: Record<string, unknown> = {
    question: query,
    top_k: topK,
    similarity_threshold: similarityThreshold,
    use_kg: useKg,
  };
  if (datasetIds?.length) {
    body.dataset_ids = datasetIds;
  }

  console.log('[ragflow] Searching:', query, datasetIds ? `datasets=${datasetIds.join(',')}` : '(all)');

  try {
    const res = await fetch(`${getUrl()}/api/v1/retrieval`, {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });

    if (!res.ok) {
      console.error(`[ragflow] Retrieval API returned ${res.status}: ${await res.text()}`);
      return [];
    }

    const json = await res.json();
    const chunks: RagflowChunk[] = (json.data?.chunks ?? []).map((c: any) => ({
      content: c.content ?? '',
      document_name: c.document_name ?? c.doc_name ?? '',
      dataset_name: c.dataset_name ?? c.kb_name ?? '',
      similarity_score: c.similarity ?? c.score ?? 0,
      metadata: c.metadata ?? {},
    }));

    console.log(`[ragflow] Found ${chunks.length} chunks for "${query.slice(0, 50)}"`);
    return chunks;
  } catch (err) {
    console.error('[ragflow] Search error:', err);
    return [];
  }
}

// ── Datasets ─────────────────────────────────────────────────────────────────

export async function listDatasets(): Promise<RagflowDataset[]> {
  if (!checkKey()) return [];

  try {
    const res = await fetch(`${getUrl()}/api/v1/datasets`, {
      headers: headers(),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });

    if (!res.ok) {
      console.error(`[ragflow] List datasets returned ${res.status}`);
      return [];
    }

    const json = await res.json();
    return (json.data ?? []).map((d: any) => ({
      id: d.id,
      name: d.name,
      chunk_method: d.chunk_method ?? d.parser_id ?? 'naive',
      language: d.language ?? 'French',
      document_count: d.document_count ?? d.doc_num ?? 0,
    }));
  } catch (err) {
    console.error('[ragflow] List datasets error:', err);
    return [];
  }
}

export async function createDataset(
  name: string,
  chunkMethod = 'naive',
  language = 'French',
): Promise<RagflowDataset | null> {
  if (!checkKey()) return null;

  console.log(`[ragflow] Creating dataset: "${name}" (method=${chunkMethod}, lang=${language})`);

  try {
    const res = await fetch(`${getUrl()}/api/v1/datasets`, {
      method: 'POST',
      headers: headers(),
      body: JSON.stringify({
        name,
        chunk_method: chunkMethod,
      }),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });

    if (!res.ok) {
      const text = await res.text();
      console.error(`[ragflow] Create dataset returned ${res.status}: ${text}`);
      return null;
    }

    const json = await res.json();
    if (json.code !== 0) {
      console.error(`[ragflow] Create dataset error: ${json.message}`);
      return null;
    }
    const d = json.data;
    console.log(`[ragflow] Dataset created: "${name}" (id=${d?.id})`);
    return d
      ? {
          id: d.id,
          name: d.name,
          chunk_method: d.chunk_method ?? d.parser_id ?? chunkMethod,
          language: d.language ?? 'French',
          document_count: 0,
        }
      : null;
  } catch (err) {
    console.error('[ragflow] Create dataset error:', err);
    return null;
  }
}
