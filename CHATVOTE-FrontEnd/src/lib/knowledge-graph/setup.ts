/**
 * Apply Knowledge Graph configuration to RAGFlow datasets.
 *
 * Idempotent: creates missing datasets, updates parser_config on existing ones.
 * Can be called from seed script or at startup to ensure config is in sync.
 *
 * Usage:
 *   import { syncDatasets } from '@lib/knowledge-graph/setup';
 *   await syncDatasets(partyIds);
 */

import {
  createDataset,
  listDatasets,
  type RagflowDataset,
} from '@lib/ai/ragflow-client';
import {
  DATASET_PRESETS,
  getPartyDatasetPreset,
  type DatasetPreset,
} from './config';

const RAGFLOW_URL = () => process.env.RAGFLOW_API_URL ?? 'http://localhost:8680';
const RAGFLOW_KEY = () => process.env.RAGFLOW_API_KEY;

// ── Update dataset parser_config via RAGFlow API ─────────────────────────────

async function updateDatasetConfig(
  datasetId: string,
  preset: DatasetPreset,
): Promise<boolean> {
  const key = RAGFLOW_KEY();
  if (!key) return false;

  const body: Record<string, unknown> = {};
  if (preset.description) body.description = preset.description;
  if (preset.parser_config) body.parser_config = preset.parser_config;

  try {
    const res = await fetch(`${RAGFLOW_URL()}/api/v1/datasets/${datasetId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${key}`,
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(10_000),
    });

    if (!res.ok) {
      console.error(`[kg-setup] Failed to update dataset ${datasetId}: ${res.status}`);
      return false;
    }

    const json = await res.json();
    if (json.code !== 0) {
      console.error(`[kg-setup] Update error for ${datasetId}: ${json.message}`);
      return false;
    }

    return true;
  } catch (err) {
    console.error(`[kg-setup] Update error for ${datasetId}:`, err);
    return false;
  }
}

// ── Sync a single dataset preset ─────────────────────────────────────────────

async function syncPreset(
  preset: DatasetPreset,
  existingByName: Map<string, RagflowDataset>,
): Promise<{ action: 'created' | 'updated' | 'skipped' | 'error'; name: string }> {
  const existing = existingByName.get(preset.name);

  if (existing) {
    // Dataset exists — update config if parser_config provided
    if (preset.parser_config) {
      const ok = await updateDatasetConfig(existing.id, preset);
      return { action: ok ? 'updated' : 'error', name: preset.name };
    }
    return { action: 'skipped', name: preset.name };
  }

  // Create new dataset
  const result = await createDataset(preset.name, preset.chunk_method);
  if (!result) {
    return { action: 'error', name: preset.name };
  }

  // Apply parser_config after creation
  if (preset.parser_config && result.id) {
    await updateDatasetConfig(result.id, preset);
  }

  return { action: 'created', name: preset.name };
}

// ── Main sync function ───────────────────────────────────────────────────────

export interface SyncResult {
  created: string[];
  updated: string[];
  skipped: string[];
  errors: string[];
}

/**
 * Synchronize RAGFlow datasets with the configured presets.
 * Creates missing datasets and updates parser_config (including GraphRAG settings)
 * on existing ones.
 *
 * @param partyIds — Party IDs to create per-party manifesto datasets for
 * @param partyNames — Optional map of partyId → display name
 */
export async function syncDatasets(
  partyIds: string[] = [],
  partyNames: Map<string, string> = new Map(),
): Promise<SyncResult> {
  const result: SyncResult = { created: [], updated: [], skipped: [], errors: [] };

  // Fetch existing datasets
  const existing = await listDatasets();
  const existingByName = new Map(existing.map((d) => [d.name, d]));

  console.log(`[kg-setup] Found ${existing.length} existing datasets, syncing ${DATASET_PRESETS.length + partyIds.length} presets...`);

  // Sync global presets
  const allPresets: DatasetPreset[] = [
    ...DATASET_PRESETS,
    ...partyIds.map((id) => getPartyDatasetPreset(id, partyNames.get(id))),
  ];

  // Process sequentially to avoid rate limits
  for (const preset of allPresets) {
    const r = await syncPreset(preset, existingByName);
    result[r.action === 'error' ? 'errors' : `${r.action}` as keyof SyncResult].push(r.name);
  }

  console.log(`[kg-setup] Sync complete: ${result.created.length} created, ${result.updated.length} updated, ${result.skipped.length} skipped, ${result.errors.length} errors`);

  return result;
}
