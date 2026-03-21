import { createOpenAICompatible } from '@ai-sdk/openai-compatible';

// Scaleway OpenAI-compatible provider (embeddings + chat)
const scaleway = createOpenAICompatible({
  name: 'scaleway',
  baseURL: process.env.SCALEWAY_EMBED_BASE_URL || 'https://api.scaleway.ai/v1',
  apiKey: process.env.SCALEWAY_EMBED_API_KEY,
});

export const embeddingModel = scaleway.textEmbeddingModel('qwen3-embedding-8b');

// Scaleway chat model — Qwen 3.5 397B MoE (250k context, 16k output)
export const scalewayChat = scaleway.languageModel('qwen3.5-397b-a17b');
