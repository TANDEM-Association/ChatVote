import type { ChatPipelineResult } from '@lib/ai/chat-pipeline';

const DEBUG = process.env.DEBUG_QUERIES === 'true';

export function logPipelineResult(label: string, result: ChatPipelineResult): void {
  if (!DEBUG) return;

  console.log(`\n${'─'.repeat(70)}`);
  console.log(`── Item: "${label}"`);
  console.log(`${'─'.repeat(70)}`);

  for (const step of result.steps) {
    if (step.toolCalls.length > 0) {
      for (const tc of step.toolCalls) {
        console.log(`Step ${step.stepNumber}: ${tc.toolName}(${JSON.stringify(tc.args).slice(0, 200)})`);
      }
    }
    if (step.text) {
      console.log(`Step ${step.stepNumber}: text generation (${step.text.length} chars)`);
    }
  }

  console.log(`\nTool calls: ${result.toolCalls.length}`);
  for (const tc of result.toolCalls) {
    console.log(`  [${tc.stepNumber}] ${tc.toolName}: ${tc.resultPreview}`);
  }

  console.log(`\nSources: ${result.sources.length}`);
  for (const s of result.sources.slice(0, 5)) {
    console.log(`  [${s.id}] score=${s.score?.toFixed(3)} party=${s.party_id ?? '-'} candidate=${s.candidate_name ?? '-'}`);
    console.log(`       ${s.content.slice(0, 100)}...`);
  }

  const citations = result.output.match(/\[\d+\]/g) ?? [];
  console.log(`\nCitations in output: ${new Set(citations).size} unique`);
  console.log(`Usage: ${result.usage.promptTokens}p + ${result.usage.completionTokens}c = ${result.usage.totalTokens} tokens`);
  console.log(`${'─'.repeat(70)}\n`);
}
