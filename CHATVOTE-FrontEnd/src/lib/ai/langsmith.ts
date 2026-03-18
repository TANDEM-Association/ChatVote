import * as ai from 'ai';
import { wrapAISDK } from 'langsmith/experimental/vercel';

// Wrap AI SDK with LangSmith tracing (no-op if LANGCHAIN_TRACING is not set)
const wrapped = wrapAISDK(ai);

export const streamText = wrapped.streamText;
export const generateText = wrapped.generateText;
