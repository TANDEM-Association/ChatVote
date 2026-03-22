// Knowledge Graph — RAGFlow GraphRAG configuration & types
//
// config.ts  — Political entity types, dataset presets, parser configs (versioned)
// types.ts   — Zod schemas for RAGFlow API responses (KG nodes, edges, retrieval)
// setup.ts   — Sync config to RAGFlow datasets via API (idempotent)

export {
  // Entity types
  POLITICAL_ENTITY_TYPES,
  type PoliticalEntityType,
  // GraphRAG config
  GraphRAGConfigSchema,
  type GraphRAGConfig,
  DEFAULT_GRAPHRAG_CONFIG,
  DEFAULT_RAPTOR_CONFIG,
  // Parser config
  ParserConfigSchema,
  type ParserConfig,
  MANIFESTO_PARSER_CONFIG,
  WEBSITE_PARSER_CONFIG,
  // Dataset presets
  DATASET_PRESETS,
  getPartyDatasetPreset,
  DatasetPresetSchema,
  type DatasetPreset,
  ChunkMethodSchema,
  type ChunkMethod,
} from './config';

export {
  // KG response types
  KGNodeSchema,
  type KGNode,
  KGEdgeSchema,
  type KGEdge,
  KnowledgeGraphSchema,
  type KnowledgeGraph,
  KGTraceStatusSchema,
  type KGTraceStatus,
  // Retrieval types
  RetrievalChunkSchema,
  type RetrievalChunk,
  RetrievalResponseSchema,
  type RetrievalResponse,
  KGResponseSchema,
  type KGResponse,
  // Dataset info
  DatasetInfoSchema,
  type DatasetInfo,
  // Generic response
  RAGFlowResponseSchema,
  type RAGFlowResponse,
} from './types';

export { syncDatasets, type SyncResult } from './setup';
