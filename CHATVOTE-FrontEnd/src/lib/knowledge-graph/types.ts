/**
 * Zod schemas for RAGFlow API responses related to Knowledge Graph.
 *
 * These type the data we GET from RAGFlow — nodes, edges, retrieval chunks,
 * and dataset metadata. They don't define the graph structure itself
 * (RAGFlow does that internally during parsing).
 */

import { z } from 'zod/v4';

// ── Knowledge Graph Node ─────────────────────────────────────────────────────
// Returned by GET /api/v1/datasets/{dataset_id}/knowledge_graph

export const KGNodeSchema = z.object({
  id: z.string(),
  entity_name: z.string(),
  entity_type: z.string(),
  description: z.string().optional(),
  pagerank: z.number().optional(),
  rank: z.number().optional(),
  source_id: z.array(z.string()).optional(),
});

export type KGNode = z.infer<typeof KGNodeSchema>;

// ── Knowledge Graph Edge ─────────────────────────────────────────────────────

export const KGEdgeSchema = z.object({
  src_id: z.string(),
  tgt_id: z.string(),
  weight: z.number().optional(),
  description: z.string().optional(),
});

export type KGEdge = z.infer<typeof KGEdgeSchema>;

// ── Knowledge Graph Response ─────────────────────────────────────────────────

export const KnowledgeGraphSchema = z.object({
  nodes: z.array(KGNodeSchema),
  edges: z.array(KGEdgeSchema),
  multigraph: z.boolean().optional(),
  graph: z.object({
    source_id: z.array(z.string()).optional(),
  }).optional(),
});

export type KnowledgeGraph = z.infer<typeof KnowledgeGraphSchema>;

// ── KG Construction Status ───────────────────────────────────────────────────
// Returned by GET /api/v1/datasets/{dataset_id}/trace_graphrag

export const KGTraceStatusSchema = z.object({
  code: z.number(),
  data: z.object({
    status: z.string().optional(),
    progress: z.number().optional(),
    message: z.string().optional(),
  }).optional(),
});

export type KGTraceStatus = z.infer<typeof KGTraceStatusSchema>;

// ── RAGFlow Retrieval Chunk ──────────────────────────────────────────────────
// Returned by POST /api/v1/retrieval in data.chunks[]

export const RetrievalChunkSchema = z.object({
  id: z.string().optional(),
  content: z.string(),
  document_id: z.string().optional(),
  document_name: z.string().optional(),
  dataset_id: z.string().optional(),
  dataset_name: z.string().optional(),
  similarity: z.number().optional(),
  score: z.number().optional(),
  // KG-enhanced fields (present when use_kg=true)
  entity_name: z.string().optional(),
  entity_type: z.string().optional(),
  // Chunk metadata
  image_id: z.string().optional(),
  important_keywords: z.union([z.string(), z.array(z.string())]).optional(),
  positions: z.array(z.string()).optional(),
});

export type RetrievalChunk = z.infer<typeof RetrievalChunkSchema>;

// ── RAGFlow API Response Wrappers ────────────────────────────────────────────

export const RAGFlowResponseSchema = z.object({
  code: z.number(),
  message: z.string().optional(),
  data: z.unknown().optional(),
});

export type RAGFlowResponse = z.infer<typeof RAGFlowResponseSchema>;

export const RetrievalResponseSchema = z.object({
  code: z.number(),
  message: z.string().optional(),
  data: z.object({
    chunks: z.array(RetrievalChunkSchema),
    total: z.number().optional(),
  }).optional(),
});

export type RetrievalResponse = z.infer<typeof RetrievalResponseSchema>;

export const KGResponseSchema = z.object({
  code: z.number(),
  message: z.string().optional(),
  data: KnowledgeGraphSchema.optional(),
});

export type KGResponse = z.infer<typeof KGResponseSchema>;

// ── Dataset Info ─────────────────────────────────────────────────────────────
// Returned by GET /api/v1/datasets

export const DatasetInfoSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().optional().nullable(),
  chunk_method: z.string(),
  chunk_count: z.number(),
  document_count: z.number(),
  token_num: z.number(),
  embedding_model: z.string(),
  language: z.string().optional(),
  similarity_threshold: z.number().optional(),
  vector_similarity_weight: z.number().optional(),
  status: z.string().optional(),
  parser_config: z.object({
    graphrag: z.object({
      use_graphrag: z.boolean(),
      method: z.string().optional(),
      entity_types: z.array(z.string()).optional(),
    }).optional(),
    raptor: z.object({
      use_raptor: z.boolean(),
    }).optional(),
    chunk_token_num: z.number().optional(),
    auto_keywords: z.number().optional(),
    auto_questions: z.number().optional(),
  }).optional(),
  create_date: z.string().optional(),
  update_date: z.string().optional(),
});

export type DatasetInfo = z.infer<typeof DatasetInfoSchema>;
