// Deterministic evaluators — no LLM calls, instant scoring

interface ToolCall {
  toolName: string;
  args: Record<string, unknown>;
}

interface EvalInput {
  output: string;
  expected?: string;
  metadata?: Record<string, unknown>;
  input?: string;
}

const RAG_TOOLS = [
  'searchPartyManifesto',
  'searchCandidateWebsite',
  'searchAllCandidates',
  'searchVotingRecords',
  'searchParliamentaryQuestions',
  'searchDataGouv',
  'runDeepResearch',
];

const EDGE_CASE_CATEGORIES = [
  'refusal_to_recommend',
  'refusal_to_rank',
  'prompt_injection',
  'off_topic',
];

function getToolCalls(metadata: Record<string, unknown> | undefined): ToolCall[] {
  return ((metadata as any)?._toolCalls ?? []) as ToolCall[];
}

function isEdgeCase(metadata: Record<string, unknown> | undefined): boolean {
  const category = (metadata as any)?.category as string;
  return EDGE_CASE_CATEGORIES.includes(category);
}

/** Did the model call at least 1 RAG search tool? */
export async function toolCallCountScorer({ output, metadata }: EvalInput) {
  const toolCalls = getToolCalls(metadata);
  const ragCallCount = toolCalls.filter((tc) => RAG_TOOLS.includes(tc.toolName)).length;

  if (isEdgeCase(metadata)) {
    return { score: 1.0, metadata: { comment: `Edge case — ${ragCallCount} RAG calls (OK)` } };
  }

  return {
    score: ragCallCount > 0 ? 1.0 : 0.0,
    metadata: { comment: `${ragCallCount} RAG tool calls` },
  };
}

/** Were sources cited in the output using [N] notation? */
export async function sourceCountScorer({ output, metadata }: EvalInput) {
  const citations = output.match(/\[\d+\]/g) ?? [];
  const uniqueCitations = new Set(citations);

  if (isEdgeCase(metadata)) {
    return { score: 1.0, metadata: { comment: `Edge case — ${uniqueCitations.size} citations (OK)` } };
  }

  return {
    score: uniqueCitations.size > 0 ? 1.0 : 0.0,
    metadata: { comment: `${uniqueCitations.size} unique citations found` },
  };
}

/** Did it query the expected parties/candidates? */
export async function expectedPartyMatchScorer({ metadata }: EvalInput) {
  const expectedPartyIds = ((metadata as any)?.party_ids ?? []) as string[];
  const toolCalls = getToolCalls(metadata);

  if (expectedPartyIds.length === 0) {
    return { score: 1.0, metadata: { comment: 'No expected parties (edge case)' } };
  }

  const queriedPartyIds = new Set<string>();
  for (const tc of toolCalls) {
    if (tc.toolName === 'searchPartyManifesto' && tc.args.partyId) {
      queriedPartyIds.add(String(tc.args.partyId).toLowerCase());
    }
  }

  const matched = expectedPartyIds.filter((id) => queriedPartyIds.has(id.toLowerCase()));
  const ratio = matched.length / expectedPartyIds.length;

  return {
    score: ratio,
    metadata: { comment: `Queried ${matched.length}/${expectedPartyIds.length} expected parties: ${[...queriedPartyIds].join(', ')}` },
  };
}

/** Are search queries non-trivial (not empty, different from input)? */
export async function queryQualityScorer({ input, metadata }: EvalInput) {
  const toolCalls = getToolCalls(metadata);
  const ragCalls = toolCalls.filter((tc) =>
    ['searchPartyManifesto', 'searchCandidateWebsite', 'searchAllCandidates'].includes(tc.toolName),
  );

  if (ragCalls.length === 0) {
    return { score: 1.0, metadata: { comment: 'No RAG calls to evaluate' } };
  }

  let goodQueries = 0;
  let totalQueries = 0;

  for (const tc of ragCalls) {
    const query = String(tc.args.query ?? tc.args.queries ?? '');
    totalQueries++;
    if (
      query.trim().length > 5 &&
      query.split(/\s+/).length >= 3 &&
      query.trim().toLowerCase() !== (input ?? '').trim().toLowerCase()
    ) {
      goodQueries++;
    }
  }

  const ratio = totalQueries > 0 ? goodQueries / totalQueries : 1;
  return {
    score: ratio,
    metadata: { comment: `${goodQueries}/${totalQueries} queries are well-formed` },
  };
}
