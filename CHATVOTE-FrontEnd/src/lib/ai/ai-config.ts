import { db } from '@lib/firebase/firebase-admin';

export interface AiConfig {
  maxSearchCalls: number;
  docsPerCandidateShallow: number;
  docsPerCandidateDeep: number;
  docsPerSearchShallow: number;
  docsPerSearchDeep: number;
  scoreThreshold: number;
  primaryModel: string;
  fallbackModel: string;
  rateLimitMax: number;
  enablePerplexity: boolean;
}

export const AI_CONFIG_DEFAULTS: AiConfig = {
  maxSearchCalls: 3,
  docsPerCandidateShallow: 3,
  docsPerCandidateDeep: 5,
  docsPerSearchShallow: 6,
  docsPerSearchDeep: 8,
  scoreThreshold: 0.25,
  primaryModel: 'scaleway-qwen',
  fallbackModel: 'gemini-2.5-flash',
  rateLimitMax: 20,
  enablePerplexity: false,
};

let cached: AiConfig | null = null;
let cachedAt = 0;
const TTL = 60_000;

export async function getAiConfig(): Promise<AiConfig> {
  const now = Date.now();
  if (cached && now - cachedAt < TTL) return cached;

  try {
    const doc = await db.collection('system_status').doc('ai_config').get();
    const data = doc.exists ? doc.data() : {};
    cached = { ...AI_CONFIG_DEFAULTS, ...data } as AiConfig;
    cachedAt = now;
    return cached;
  } catch (err) {
    console.error('[ai-config] Failed to fetch config, using defaults:', err);
    return AI_CONFIG_DEFAULTS;
  }
}
