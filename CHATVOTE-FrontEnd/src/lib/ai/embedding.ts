import { embed } from 'ai';
import { embeddingModel } from './providers';

export async function embedQuery(query: string): Promise<number[]> {
  const start = Date.now();
  try {
    const { embedding } = await embed({
      model: embeddingModel,
      value: query,
    });
    console.log(`[ai-chat:embed] OK dim=${embedding.length} ${Date.now() - start}ms q="${query.slice(0, 60)}"`);
    return embedding;
  } catch (err) {
    console.error(`[ai-chat:embed] FAILED ${Date.now() - start}ms q="${query.slice(0, 60)}"`, err);
    throw err;
  }
}
