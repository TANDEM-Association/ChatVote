import 'server-only';

import * as ai from 'ai';
import { wrapAISDK } from 'langsmith/experimental/vercel';

// ── Langfuse setup ────────────────────────────────────────────────────────────
//
// Tracing is handled by the LangfuseSpanProcessor registered in
// instrumentation.ts (OpenTelemetry-based). All we need to do here is:
//   1. Enable experimental_telemetry on every AI SDK call
//   2. Expose the Langfuse SDK singleton for custom spans (e.g. Qdrant search)
//

const LANGFUSE_SECRET_KEY = process.env.LANGFUSE_SECRET_KEY;
const LANGFUSE_PUBLIC_KEY = process.env.LANGFUSE_PUBLIC_KEY;
const LANGFUSE_BASEURL = process.env.LANGFUSE_BASEURL ?? 'http://localhost:8652';

const langfuseEnabled = Boolean(LANGFUSE_SECRET_KEY);

// Lazy singleton — only instantiated when Langfuse is enabled.
// Used for custom spans (Qdrant search, etc.) outside of AI SDK calls.
let _langfuseInstance: InstanceType<typeof import('langfuse').Langfuse> | null = null;

export function getLangfuse(): InstanceType<typeof import('langfuse').Langfuse> | null {
  if (!langfuseEnabled) return null;

  if (!_langfuseInstance) {
    // Dynamic require to avoid loading the module when not configured
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { Langfuse } = require('langfuse') as typeof import('langfuse');
    _langfuseInstance = new Langfuse({
      secretKey: LANGFUSE_SECRET_KEY,
      publicKey: LANGFUSE_PUBLIC_KEY,
      baseUrl: LANGFUSE_BASEURL,
    });
  }

  return _langfuseInstance;
}

// ── Wrapped streamText / generateText ────────────────────────────────────────

type StreamTextParams = Parameters<typeof ai.streamText>[0];
type StreamTextReturn = ReturnType<typeof ai.streamText>;

type GenerateTextParams = Parameters<typeof ai.generateText>[0];
type GenerateTextReturn = ReturnType<typeof ai.generateText>;

// ── LangSmith wrapped SDK (hoisted to avoid double wrapAISDK call) ───────────

const _langsmithWrapped = (!langfuseEnabled && process.env.LANGCHAIN_TRACING === 'true')
  ? wrapAISDK(ai)
  : null;

// ── Provider selection ────────────────────────────────────────────────────────

function makeStreamText(): (params: StreamTextParams) => StreamTextReturn {
  if (langfuseEnabled) {
    return (params: StreamTextParams): StreamTextReturn => {
      return ai.streamText({
        ...params,
        experimental_telemetry: {
          isEnabled: true,
          ...params.experimental_telemetry,
        },
      });
    };
  }

  if (_langsmithWrapped) {
    return _langsmithWrapped.streamText as (params: StreamTextParams) => StreamTextReturn;
  }

  return ai.streamText as (params: StreamTextParams) => StreamTextReturn;
}

function makeGenerateText(): (params: GenerateTextParams) => GenerateTextReturn {
  if (langfuseEnabled) {
    return (params: GenerateTextParams): GenerateTextReturn => {
      return ai.generateText({
        ...params,
        experimental_telemetry: {
          isEnabled: true,
          ...params.experimental_telemetry,
        },
      });
    };
  }

  if (_langsmithWrapped) {
    return _langsmithWrapped.generateText as (params: GenerateTextParams) => GenerateTextReturn;
  }

  return ai.generateText as (params: GenerateTextParams) => GenerateTextReturn;
}

export const streamText = makeStreamText();
export const generateText = makeGenerateText();

// ── Flush (call at end of serverless request) ────────────────────────────────

export async function flushLangfuse(): Promise<void> {
  if (_langfuseInstance) {
    await _langfuseInstance.flushAsync();
  }
}
