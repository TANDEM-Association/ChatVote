import 'server-only';

import * as ai from 'ai';
import { wrapAISDK } from 'langsmith/experimental/vercel';

// ── Langfuse setup ────────────────────────────────────────────────────────────
//
// Tracing is handled by the LangfuseSpanProcessor registered in
// instrumentation.ts (OpenTelemetry-based). All we need to do here is:
//   1. Enable experimental_telemetry on every AI SDK call
//   2. For custom spans (e.g. Qdrant search), use observe() from @langfuse/tracing
//      directly in the calling module — no Langfuse SDK singleton needed here.
//

const langfuseEnabled = Boolean(process.env.LANGFUSE_SECRET_KEY);

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
