import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { searchRagflow, listDatasets, createDataset } from '@lib/ai/ragflow-client';

// ── Mock fetch globally ──────────────────────────────────────────────────────
const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

function jsonResponse(data: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
  });
}

describe('ragflow-client', () => {
  const ORIGINAL_ENV = { ...process.env };

  beforeEach(() => {
    process.env.RAGFLOW_API_KEY = 'test-key-123';
    process.env.RAGFLOW_API_URL = 'http://ragflow-test:9380';
    mockFetch.mockReset();
  });

  afterEach(() => {
    process.env = { ...ORIGINAL_ENV };
  });

  // ── searchRagflow ──────────────────────────────────────────────────────────

  describe('searchRagflow', () => {
    it('returns empty array when RAGFLOW_API_KEY is not set', async () => {
      delete process.env.RAGFLOW_API_KEY;
      const result = await searchRagflow('test query');
      expect(result).toEqual([]);
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it('calls POST /api/v1/retrieval with correct body', async () => {
      mockFetch.mockReturnValueOnce(jsonResponse({ code: 0, data: { chunks: [] } }));

      await searchRagflow('ecologie', undefined, 5, 0.3);

      expect(mockFetch).toHaveBeenCalledOnce();
      const [url, opts] = mockFetch.mock.calls[0];
      expect(url).toBe('http://ragflow-test:9380/api/v1/retrieval');
      expect(opts.method).toBe('POST');
      expect(opts.headers.Authorization).toBe('Bearer test-key-123');

      const body = JSON.parse(opts.body);
      expect(body.question).toBe('ecologie');
      expect(body.top_k).toBe(5);
      expect(body.similarity_threshold).toBe(0.3);
      expect(body.dataset_ids).toBeUndefined();
    });

    it('passes dataset_ids when provided', async () => {
      mockFetch.mockReturnValueOnce(jsonResponse({ code: 0, data: { chunks: [] } }));

      await searchRagflow('test', ['ds-1', 'ds-2']);

      const body = JSON.parse(mockFetch.mock.calls[0][1].body);
      expect(body.dataset_ids).toEqual(['ds-1', 'ds-2']);
    });

    it('maps chunk response fields correctly', async () => {
      mockFetch.mockReturnValueOnce(jsonResponse({
        code: 0,
        data: {
          chunks: [
            {
              content: 'Le programme écologique prévoit...',
              document_name: 'programme-eelv.pdf',
              dataset_name: 'manifesto-eelv',
              similarity: 0.87,
              metadata: { party_id: 'eelv', candidate_name: 'Jean Dupont' },
            },
            {
              content: 'Transition énergétique...',
              doc_name: 'site-web.html',
              kb_name: 'candidates-websites',
              score: 0.72,
            },
          ],
        },
      }));

      const results = await searchRagflow('ecologie');

      expect(results).toHaveLength(2);
      expect(results[0]).toEqual({
        content: 'Le programme écologique prévoit...',
        document_name: 'programme-eelv.pdf',
        dataset_name: 'manifesto-eelv',
        similarity_score: 0.87,
        metadata: { party_id: 'eelv', candidate_name: 'Jean Dupont' },
      });
      // Fallback field names (doc_name, kb_name, score)
      expect(results[1].document_name).toBe('site-web.html');
      expect(results[1].dataset_name).toBe('candidates-websites');
      expect(results[1].similarity_score).toBe(0.72);
      expect(results[1].metadata).toEqual({});
    });

    it('returns empty array on HTTP error', async () => {
      mockFetch.mockReturnValueOnce(jsonResponse({ error: 'Server error' }, 500));

      const results = await searchRagflow('test');
      expect(results).toEqual([]);
    });

    it('returns empty array when code is non-zero (e.g. no chunks)', async () => {
      mockFetch.mockReturnValueOnce(jsonResponse({
        code: 102,
        data: null,
        message: 'No chunk found!',
      }));

      const results = await searchRagflow('test');
      expect(results).toEqual([]);
    });

    it('returns empty array on fetch error (timeout, network)', async () => {
      mockFetch.mockRejectedValueOnce(new Error('AbortError: signal timed out'));

      const results = await searchRagflow('test');
      expect(results).toEqual([]);
    });
  });

  // ── listDatasets ───────────────────────────────────────────────────────────

  describe('listDatasets', () => {
    it('returns empty array when RAGFLOW_API_KEY is not set', async () => {
      delete process.env.RAGFLOW_API_KEY;
      const result = await listDatasets();
      expect(result).toEqual([]);
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it('calls GET /api/v1/datasets with auth header', async () => {
      mockFetch.mockReturnValueOnce(jsonResponse({ code: 0, data: [] }));

      await listDatasets();

      const [url, opts] = mockFetch.mock.calls[0];
      expect(url).toBe('http://ragflow-test:9380/api/v1/datasets');
      expect(opts.headers.Authorization).toBe('Bearer test-key-123');
      expect(opts.method).toBeUndefined(); // GET is default
    });

    it('maps dataset response fields correctly', async () => {
      mockFetch.mockReturnValueOnce(jsonResponse({
        code: 0,
        data: [
          { id: 'ds-1', name: 'all-manifestos', chunk_method: 'laws', language: 'French', document_count: 5 },
          { id: 'ds-2', name: 'candidates', parser_id: 'naive', doc_num: 12 },
        ],
      }));

      const datasets = await listDatasets();

      expect(datasets).toHaveLength(2);
      expect(datasets[0]).toEqual({
        id: 'ds-1', name: 'all-manifestos', chunk_method: 'laws', language: 'French', document_count: 5,
      });
      // Fallback field names
      expect(datasets[1].chunk_method).toBe('naive');
      expect(datasets[1].document_count).toBe(12);
    });

    it('returns empty array on error', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'));
      const result = await listDatasets();
      expect(result).toEqual([]);
    });
  });

  // ── createDataset ──────────────────────────────────────────────────────────

  describe('createDataset', () => {
    it('returns null when RAGFLOW_API_KEY is not set', async () => {
      delete process.env.RAGFLOW_API_KEY;
      const result = await createDataset('test');
      expect(result).toBeNull();
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it('calls POST /api/v1/datasets with name and chunk_method', async () => {
      mockFetch.mockReturnValueOnce(jsonResponse({
        code: 0,
        data: { id: 'new-ds', name: 'my-dataset', chunk_method: 'laws', language: 'English', document_count: 0 },
      }));

      const result = await createDataset('my-dataset', 'laws');

      const [url, opts] = mockFetch.mock.calls[0];
      expect(url).toBe('http://ragflow-test:9380/api/v1/datasets');
      expect(opts.method).toBe('POST');

      const body = JSON.parse(opts.body);
      expect(body.name).toBe('my-dataset');
      expect(body.chunk_method).toBe('laws');
      // language should NOT be in the body (RAGFlow rejects it)
      expect(body.language).toBeUndefined();

      expect(result).toEqual({
        id: 'new-ds', name: 'my-dataset', chunk_method: 'laws', language: 'English', document_count: 0,
      });
    });

    it('returns null when RAGFlow returns non-zero code', async () => {
      mockFetch.mockReturnValueOnce(jsonResponse({
        code: 101,
        message: 'Field: <language> - Extra inputs not permitted',
      }));

      const result = await createDataset('test');
      expect(result).toBeNull();
    });

    it('returns null on network error', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Connection refused'));
      const result = await createDataset('test');
      expect(result).toBeNull();
    });
  });
});
