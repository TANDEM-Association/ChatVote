/**
 * Knowledge Graph configuration for RAGFlow GraphRAG.
 *
 * Defines the political domain entity types and dataset configurations
 * that RAGFlow uses for automatic entity extraction during document parsing.
 * This is the versioned source of truth — changes here propagate to RAGFlow
 * via the setup script (setup.ts).
 *
 * RAGFlow rebuilds the KG from documents + this config on each parse.
 * There is no KG export/import — the config IS the version control.
 */

import { z } from 'zod/v4';

// ── Political Entity Types ───────────────────────────────────────────────────
// Custom entity types for French political domain.
// RAGFlow extracts these from documents during parsing (replaces default
// organization/person/geo/event/category).

export const POLITICAL_ENTITY_TYPES = [
  'personnalite_politique',  // Candidat, élu, tête de liste
  'parti_politique',         // Organisation politique (Renaissance, LFI, RN, PS…)
  'coalition',               // Alliance de partis pour un scrutin
  'institution',             // Assemblée Nationale, Sénat, Conseil Municipal…
  'election',                // Scrutin (présidentielle, législative, municipale…)
  'localisation',            // Commune, département, région, circonscription
  'theme',                   // Sujet politique (écologie, sécurité, logement…)
  'media',                   // Source éditoriale (journal, chaîne YouTube…)
  'mandat',                  // Fonction politique (maire, député, ministre…)
  'liste_electorale',        // Groupement de candidats pour un scrutin de liste
] as const;

export type PoliticalEntityType = (typeof POLITICAL_ENTITY_TYPES)[number];

// ── GraphRAG Method ──────────────────────────────────────────────────────────

export const GraphRAGMethodSchema = z.enum(['light', 'general']);
export type GraphRAGMethod = z.infer<typeof GraphRAGMethodSchema>;

// ── GraphRAG Configuration ───────────────────────────────────────────────────
// Maps to RAGFlow's parser_config.graphrag object

export const GraphRAGConfigSchema = z.object({
  use_graphrag: z.boolean(),
  method: GraphRAGMethodSchema,
  entity_types: z.array(z.string()),
});

export type GraphRAGConfig = z.infer<typeof GraphRAGConfigSchema>;

// ── RAPTOR Configuration ─────────────────────────────────────────────────────

export const RAPTORConfigSchema = z.object({
  use_raptor: z.boolean(),
  max_cluster: z.number().int().default(64),
  max_token: z.number().int().default(256),
  threshold: z.number().default(0.1),
});

export type RAPTORConfig = z.infer<typeof RAPTORConfigSchema>;

// ── Parser Configuration ─────────────────────────────────────────────────────
// Full parser_config for a RAGFlow dataset

export const ParserConfigSchema = z.object({
  chunk_token_num: z.number().int().default(512),
  delimiter: z.string().default('\\n'),
  auto_keywords: z.number().int().min(0).max(32).default(3),
  auto_questions: z.number().int().min(0).max(10).default(0),
  html4excel: z.boolean().default(false),
  layout_recognize: z.string().default('DeepDOC'),
  graphrag: GraphRAGConfigSchema,
  raptor: RAPTORConfigSchema,
});

export type ParserConfig = z.infer<typeof ParserConfigSchema>;

// ── Dataset Presets ──────────────────────────────────────────────────────────
// Pre-configured dataset templates for different document types.
// Used by the seed/setup script to create datasets with correct settings.

export const ChunkMethodSchema = z.enum([
  'naive', 'book', 'laws', 'paper', 'qa', 'table', 'presentation', 'one',
]);
export type ChunkMethod = z.infer<typeof ChunkMethodSchema>;

export const DatasetPresetSchema = z.object({
  name: z.string(),
  chunk_method: ChunkMethodSchema,
  description: z.string().optional(),
  parser_config: ParserConfigSchema.partial().optional(),
});

export type DatasetPreset = z.infer<typeof DatasetPresetSchema>;

// ── Default Configurations ───────────────────────────────────────────────────

/** Default GraphRAG config for political documents */
export const DEFAULT_GRAPHRAG_CONFIG: GraphRAGConfig = {
  use_graphrag: true,
  method: 'light',
  entity_types: [...POLITICAL_ENTITY_TYPES],
};

/** Default RAPTOR config (disabled — enable per dataset if needed) */
export const DEFAULT_RAPTOR_CONFIG: RAPTORConfig = {
  use_raptor: false,
  max_cluster: 64,
  max_token: 256,
  threshold: 0.1,
};

/** Default parser config for political manifestos */
export const MANIFESTO_PARSER_CONFIG: Partial<ParserConfig> = {
  chunk_token_num: 512,
  auto_keywords: 3,
  auto_questions: 0,
  layout_recognize: 'DeepDOC',
  graphrag: DEFAULT_GRAPHRAG_CONFIG,
  raptor: DEFAULT_RAPTOR_CONFIG,
};

/** Default parser config for candidate websites (simpler parsing) */
export const WEBSITE_PARSER_CONFIG: Partial<ParserConfig> = {
  chunk_token_num: 512,
  auto_keywords: 2,
  auto_questions: 0,
  graphrag: DEFAULT_GRAPHRAG_CONFIG,
  raptor: DEFAULT_RAPTOR_CONFIG,
};

// ── Dataset Presets ──────────────────────────────────────────────────────────

/** All dataset presets for ChatVote */
export const DATASET_PRESETS: DatasetPreset[] = [
  {
    name: 'all-manifestos',
    chunk_method: 'laws',
    description: 'Programmes et manifestes de tous les partis (parsing structuré loi/article)',
    parser_config: MANIFESTO_PARSER_CONFIG,
  },
  {
    name: 'candidates-websites',
    chunk_method: 'naive',
    description: 'Sites web des candidats (contenu web crawlé)',
    parser_config: WEBSITE_PARSER_CONFIG,
  },
];

/**
 * Generate per-party dataset presets dynamically from party IDs.
 * Each party gets its own manifesto dataset with laws chunking.
 */
export function getPartyDatasetPreset(partyId: string, partyName?: string): DatasetPreset {
  return {
    name: `manifesto-${partyId}`,
    chunk_method: 'laws',
    description: partyName
      ? `Programme de ${partyName}`
      : `Programme du parti ${partyId}`,
    parser_config: MANIFESTO_PARSER_CONFIG,
  };
}
