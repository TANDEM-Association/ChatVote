import { createOpenAICompatible } from '@ai-sdk/openai-compatible';

// Scaleway OpenAI-compatible provider (embeddings + chat)
const scaleway = createOpenAICompatible({
  name: 'scaleway',
  baseURL: process.env.SCALEWAY_EMBED_BASE_URL || 'https://api.scaleway.ai/v1',
  apiKey: process.env.SCALEWAY_EMBED_API_KEY,
});

export const embeddingModel = scaleway.textEmbeddingModel('qwen3-embedding-8b');

// Scaleway chat model — used as fallback when primary Gemini model fails
export const scalewayChat = scaleway.languageModel('qwen3-235b-a22b-instruct-2507');
