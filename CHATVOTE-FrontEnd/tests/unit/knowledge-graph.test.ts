import { describe, it, expect } from 'vitest';
import {
  POLITICAL_ENTITY_TYPES,
  DEFAULT_GRAPHRAG_CONFIG,
  DEFAULT_RAPTOR_CONFIG,
  MANIFESTO_PARSER_CONFIG,
  WEBSITE_PARSER_CONFIG,
  DATASET_PRESETS,
  getPartyDatasetPreset,
  GraphRAGConfigSchema,
  ParserConfigSchema,
  DatasetPresetSchema,
} from '@lib/knowledge-graph/config';
import {
  KGNodeSchema,
  KGEdgeSchema,
  KnowledgeGraphSchema,
  RetrievalChunkSchema,
  DatasetInfoSchema,
} from '@lib/knowledge-graph/types';

// ── Config Tests ─────────────────────────────────────────────────────────────

describe('knowledge-graph/config', () => {
  it('defines 10 political entity types', () => {
    expect(POLITICAL_ENTITY_TYPES).toHaveLength(10);
    expect(POLITICAL_ENTITY_TYPES).toContain('personnalite_politique');
    expect(POLITICAL_ENTITY_TYPES).toContain('parti_politique');
    expect(POLITICAL_ENTITY_TYPES).toContain('localisation');
    expect(POLITICAL_ENTITY_TYPES).toContain('theme');
    expect(POLITICAL_ENTITY_TYPES).toContain('election');
    expect(POLITICAL_ENTITY_TYPES).toContain('institution');
  });

  it('DEFAULT_GRAPHRAG_CONFIG has use_graphrag=true and all entity types', () => {
    expect(DEFAULT_GRAPHRAG_CONFIG.use_graphrag).toBe(true);
    expect(DEFAULT_GRAPHRAG_CONFIG.method).toBe('light');
    expect(DEFAULT_GRAPHRAG_CONFIG.entity_types).toEqual([...POLITICAL_ENTITY_TYPES]);
  });

  it('DEFAULT_RAPTOR_CONFIG has use_raptor=false', () => {
    expect(DEFAULT_RAPTOR_CONFIG.use_raptor).toBe(false);
  });

  it('MANIFESTO_PARSER_CONFIG includes GraphRAG enabled', () => {
    expect(MANIFESTO_PARSER_CONFIG.graphrag?.use_graphrag).toBe(true);
    expect(MANIFESTO_PARSER_CONFIG.chunk_token_num).toBe(512);
    expect(MANIFESTO_PARSER_CONFIG.auto_keywords).toBe(3);
  });

  it('WEBSITE_PARSER_CONFIG includes GraphRAG enabled', () => {
    expect(WEBSITE_PARSER_CONFIG.graphrag?.use_graphrag).toBe(true);
    expect(WEBSITE_PARSER_CONFIG.auto_keywords).toBe(2);
  });

  it('DATASET_PRESETS has 2 global presets', () => {
    expect(DATASET_PRESETS).toHaveLength(2);
    expect(DATASET_PRESETS.map((p) => p.name)).toEqual(['all-manifestos', 'candidates-websites']);
    expect(DATASET_PRESETS[0].chunk_method).toBe('laws');
    expect(DATASET_PRESETS[1].chunk_method).toBe('naive');
  });

  it('getPartyDatasetPreset generates correct preset', () => {
    const preset = getPartyDatasetPreset('renaissance', 'Renaissance');
    expect(preset.name).toBe('manifesto-renaissance');
    expect(preset.chunk_method).toBe('laws');
    expect(preset.description).toBe('Programme de Renaissance');
    expect(preset.parser_config?.graphrag?.use_graphrag).toBe(true);
  });

  it('getPartyDatasetPreset works without party name', () => {
    const preset = getPartyDatasetPreset('ps');
    expect(preset.description).toBe('Programme du parti ps');
  });

  // ── Zod Validation ─────────────────────────────────────────────────────────

  it('GraphRAGConfigSchema validates DEFAULT_GRAPHRAG_CONFIG', () => {
    const result = GraphRAGConfigSchema.safeParse(DEFAULT_GRAPHRAG_CONFIG);
    expect(result.success).toBe(true);
  });

  it('GraphRAGConfigSchema rejects invalid method', () => {
    const result = GraphRAGConfigSchema.safeParse({
      use_graphrag: true,
      method: 'invalid',
      entity_types: [],
    });
    expect(result.success).toBe(false);
  });

  it('DatasetPresetSchema validates presets', () => {
    for (const preset of DATASET_PRESETS) {
      const result = DatasetPresetSchema.safeParse(preset);
      expect(result.success).toBe(true);
    }
  });
});

// ── Types Tests ──────────────────────────────────────────────────────────────

describe('knowledge-graph/types', () => {
  it('KGNodeSchema validates a RAGFlow KG node', () => {
    const node = {
      id: 'abc123',
      entity_name: 'Emmanuel Macron',
      entity_type: 'personnalite_politique',
      description: 'Président de la République',
      pagerank: 0.85,
      rank: 1,
      source_id: ['doc-1', 'doc-2'],
    };
    const result = KGNodeSchema.safeParse(node);
    expect(result.success).toBe(true);
  });

  it('KGNodeSchema allows minimal node', () => {
    const result = KGNodeSchema.safeParse({
      id: 'x',
      entity_name: 'Test',
      entity_type: 'theme',
    });
    expect(result.success).toBe(true);
  });

  it('KGEdgeSchema validates an edge', () => {
    const result = KGEdgeSchema.safeParse({
      src_id: 'node-1',
      tgt_id: 'node-2',
      weight: 5.0,
      description: 'MEMBRE_DE',
    });
    expect(result.success).toBe(true);
  });

  it('KnowledgeGraphSchema validates full graph response', () => {
    const graph = {
      nodes: [
        { id: '1', entity_name: 'Macron', entity_type: 'personnalite_politique' },
        { id: '2', entity_name: 'Renaissance', entity_type: 'parti_politique' },
      ],
      edges: [
        { src_id: '1', tgt_id: '2', weight: 10.0 },
      ],
      multigraph: false,
      graph: { source_id: ['doc-1'] },
    };
    const result = KnowledgeGraphSchema.safeParse(graph);
    expect(result.success).toBe(true);
  });

  it('RetrievalChunkSchema validates chunk with KG fields', () => {
    const chunk = {
      content: 'Le programme écologique prévoit...',
      document_name: 'programme-eelv.pdf',
      dataset_name: 'manifesto-eelv',
      similarity: 0.87,
      entity_name: 'Europe Écologie Les Verts',
      entity_type: 'parti_politique',
    };
    const result = RetrievalChunkSchema.safeParse(chunk);
    expect(result.success).toBe(true);
  });

  it('DatasetInfoSchema validates dataset with graphrag config', () => {
    const dataset = {
      id: 'ds-1',
      name: 'all-manifestos',
      chunk_method: 'laws',
      chunk_count: 150,
      document_count: 5,
      token_num: 50000,
      embedding_model: 'gemini-embedding-001@Gemini',
      parser_config: {
        graphrag: { use_graphrag: true, method: 'light', entity_types: ['person', 'organization'] },
        raptor: { use_raptor: false },
        chunk_token_num: 512,
      },
    };
    const result = DatasetInfoSchema.safeParse(dataset);
    expect(result.success).toBe(true);
  });
});
