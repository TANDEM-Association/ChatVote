// Langfuse Experiment Runner — vitest-evals + autoevals + custom scorers
//
// Runs the AI SDK chat pipeline against golden questions, scores with:
//   - Deterministic scorers (tool calls, citations, party match, query quality)
//   - autoevals RAG scorers (faithfulness, relevancy)
//   - Custom political domain scorers (neutrality, citations, French quality)
//
// Langfuse traces are captured automatically via OTEL (experimental_telemetry
// in chat-pipeline.ts). Set LANGFUSE_SECRET_KEY + LANGFUSE_PUBLIC_KEY to enable.
//
// Usage:
//   pnpm test:eval                              # Run all eval tests
//   pnpm test:eval:debug                        # Run with query debugging
//   EVAL_CATEGORIES=single_party pnpm test:eval # Run specific category

import { describeEval } from 'vitest-evals';

import { runChatPipeline, type ChatPipelineResult } from '@lib/ai/chat-pipeline';
import { getEvalItems, type EvalItem } from './datasets/golden-questions';
import {
  toolCallCountScorer,
  sourceCountScorer,
  expectedPartyMatchScorer,
  queryQualityScorer,
} from './evaluators/deterministic';
import {
  faithfulnessScorer,
  answerRelevancyScorer,
  contextRelevancyScorer,
  politicalNeutralityScorer,
  sourceAttributionScorer,
  frenchQualityScorer,
} from './evaluators/rag-scorers';
import { logPipelineResult } from './helpers/query-debugger';

// ── Pipeline result cache (avoid re-running for multiple scorer suites) ──────

const resultCache = new Map<string, ChatPipelineResult>();

async function getOrRunPipeline(item: EvalItem): Promise<ChatPipelineResult> {
  const cacheKey = item.input;
  const cached = resultCache.get(cacheKey);
  if (cached) return cached;

  const result = await runChatPipeline({
    question: item.input,
    partyIds: item.metadata.party_ids.length > 0 ? item.metadata.party_ids : undefined,
    enabledFeatures: ['rag'],
  });

  logPipelineResult(item.input.slice(0, 60), result);
  resultCache.set(cacheKey, result);
  return result;
}

// ── Scorer adapters ──────────────────────────────────────────────────────────
// vitest-evals scorers receive { input, output, toolCalls? }
// Our custom scorers need { input, output, expected?, metadata? }
// Bridge them by looking up the eval item + cached pipeline result

function wrapScorer(
  name: string,
  scorerFn: (opts: {
    input: string;
    output: string;
    expected?: string;
    metadata?: Record<string, unknown>;
  }) => Promise<{ score: number; metadata?: Record<string, unknown> }>,
) {
  const fn = async ({ input, output }: { input: string; output: string }) => {
    const result = resultCache.get(input);
    const items = getEvalItems();
    const item = items.find((i) => i.input === input);
    const metadata: Record<string, unknown> = {
      ...(item?.metadata ?? {}),
      _sources: result?.sources ?? [],
      _toolCalls: result?.toolCalls ?? [],
    };
    return scorerFn({ input, output, expected: item?.expected, metadata });
  };
  Object.defineProperty(fn, 'name', { value: name });
  return fn;
}

// ── Category filter ──────────────────────────────────────────────────────────

const CATEGORIES = process.env.EVAL_CATEGORIES
  ? (process.env.EVAL_CATEGORIES.split(',') as Array<
      'single_party' | 'multi_party_comparison' | 'candidate_questions' | 'edge_cases'
    >)
  : undefined;

// ── Shared data loader + task runner ─────────────────────────────────────────

function evalData() {
  return async () => {
    const items = getEvalItems(CATEGORIES);
    return items.map((item) => ({
      input: item.input,
      name: `[${item.metadata.category}] ${item.input.slice(0, 60)}`,
      expected: item.expected,
      ...item.metadata,
    }));
  };
}

const evalTask = async (input: string) => {
  const items = getEvalItems(CATEGORIES);
  const item = items.find((i) => i.input === input)!;
  const result = await getOrRunPipeline(item);
  return {
    result: result.output,
    toolCalls: result.toolCalls.map((tc) => ({
      name: tc.toolName,
      arguments: tc.args,
    })),
  };
};

// ── Eval suites ──────────────────────────────────────────────────────────────

describeEval('ChatVote RAG Pipeline — Deterministic', {
  data: evalData(),
  task: evalTask,
  scorers: [
    wrapScorer('toolCallCount', toolCallCountScorer),
    wrapScorer('sourceCount', sourceCountScorer),
    wrapScorer('expectedPartyMatch', expectedPartyMatchScorer),
    wrapScorer('queryQuality', queryQualityScorer),
  ],
  threshold: 0.7,
  timeout: 180_000,
});

describeEval('ChatVote RAG Pipeline — RAG Quality', {
  data: evalData(),
  task: evalTask,
  scorers: [
    wrapScorer('faithfulness', faithfulnessScorer),
    wrapScorer('answerRelevancy', answerRelevancyScorer),
    wrapScorer('contextRelevancy', contextRelevancyScorer),
  ],
  threshold: 0.5,
  timeout: 180_000,
});

describeEval('ChatVote RAG Pipeline — Political Domain', {
  data: evalData(),
  task: evalTask,
  scorers: [
    wrapScorer('politicalNeutrality', politicalNeutralityScorer),
    wrapScorer('sourceAttribution', sourceAttributionScorer),
    wrapScorer('frenchQuality', frenchQualityScorer),
  ],
  threshold: 0.6,
  timeout: 180_000,
});
