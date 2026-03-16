import { createOpenAICompatible } from '@ai-sdk/openai-compatible';

// Scaleway OpenAI-compatible provider for embeddings (qwen3-embedding-8b, 4096d)
const scaleway = createOpenAICompatible({
  name: 'scaleway',
  baseURL: process.env.SCALEWAY_EMBED_BASE_URL || 'https://api.scaleway.ai/v1',
  apiKey: process.env.SCALEWAY_EMBED_API_KEY,
});

export const embeddingModel = scaleway.textEmbeddingModel('qwen3-embedding-8b');
