import { readFileSync } from 'fs';
import { resolve } from 'path';

interface GoldenQuestion {
  input: string;
  expected_output: string;
  party_ids?: string[];
  candidate_ids?: string[];
  expected_parties?: string[];
  expected_source_keywords?: string[];
  category: string;
}

interface GoldenDataset {
  single_party: GoldenQuestion[];
  multi_party_comparison: GoldenQuestion[];
  candidate_questions: GoldenQuestion[];
  edge_cases: GoldenQuestion[];
}

export interface EvalItem {
  input: string;
  expected: string;
  metadata: {
    party_ids: string[];
    candidate_ids: string[];
    expected_parties: string[];
    expected_source_keywords: string[];
    category: string;
  };
}

function loadGoldenDataset(): GoldenDataset {
  const jsonPath = resolve(
    __dirname,
    '../../../../CHATVOTE-BackEnd/tests/eval/datasets/golden_questions.json',
  );
  const raw = readFileSync(jsonPath, 'utf-8');
  return JSON.parse(raw);
}

export function getEvalItems(
  categories?: Array<'single_party' | 'multi_party_comparison' | 'candidate_questions' | 'edge_cases'>,
): EvalItem[] {
  const dataset = loadGoldenDataset();
  const selected = categories ?? ['single_party', 'multi_party_comparison', 'candidate_questions', 'edge_cases'];

  const items: EvalItem[] = [];

  for (const category of selected) {
    for (const q of dataset[category] ?? []) {
      items.push({
        input: q.input,
        expected: q.expected_output,
        metadata: {
          party_ids: q.party_ids ?? [],
          candidate_ids: q.candidate_ids ?? [],
          expected_parties: q.expected_parties ?? [],
          expected_source_keywords: q.expected_source_keywords ?? [],
          category: q.category,
        },
      });
    }
  }

  return items;
}
