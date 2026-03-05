"""
Auto-optimize RAG prompts using DeepEval's GEPA algorithm with Ollama.

Reads current prompt templates, evaluates them against golden test cases,
and uses genetic-Pareto optimization to find better prompt variants.

Usage:
    poetry run python scripts/optimize_prompts.py
    poetry run python scripts/optimize_prompts.py --prompt response --iterations 3
    poetry run python scripts/optimize_prompts.py --prompt query_improvement --iterations 5
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

GOLDENS_PATH = PROJECT_ROOT / "tests" / "eval" / "datasets" / "golden_questions.json"
GENERATED_GOLDENS_PATH = PROJECT_ROOT / "tests" / "eval" / "datasets" / "generated_goldens.json"
OPTIMIZED_DIR = PROJECT_ROOT / "prompts_optimized"


def _build_ollama_model():
    """Build OllamaModel for evaluation."""
    from deepeval.models import OllamaModel

    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.2")

    try:
        import urllib.request
        urllib.request.urlopen(ollama_url, timeout=3)
    except Exception:
        print(f"ERROR: Ollama not reachable at {ollama_url}")
        sys.exit(1)

    return OllamaModel(model=ollama_model, base_url=ollama_url, temperature=0.0)


def _load_goldens() -> list:
    """Load golden test cases from both hand-written and generated datasets."""
    from deepeval.dataset import Golden

    goldens = []

    # Load hand-written goldens
    if GOLDENS_PATH.exists():
        data = json.loads(GOLDENS_PATH.read_text())
        for category in ["single_party", "multi_party_comparison"]:
            for item in data.get(category, []):
                goldens.append(Golden(
                    input=item["input"],
                    expected_output=item.get("expected_output", ""),
                ))

    # Load auto-generated goldens
    if GENERATED_GOLDENS_PATH.exists():
        data = json.loads(GENERATED_GOLDENS_PATH.read_text())
        for item in data.get("generated", []):
            goldens.append(Golden(
                input=item["input"],
                expected_output=item.get("expected_output", ""),
                context=item.get("retrieval_context"),
            ))

    if not goldens:
        print("ERROR: No golden test cases found.")
        print(f"Run 'poetry run python scripts/generate_goldens.py' first,")
        print(f"or check {GOLDENS_PATH}")
        sys.exit(1)

    print(f"Loaded {len(goldens)} golden test cases")
    return goldens


def _get_current_prompts() -> dict[str, str]:
    """Extract current prompt templates from the codebase."""
    from src.prompts import (
        _get_chat_answer_guidelines_fr,
        party_response_system_prompt_template_str,
        party_comparison_system_prompt_template_str,
        system_prompt_improvement_template_str,
    )

    return {
        "response": party_response_system_prompt_template_str,
        "comparison": party_comparison_system_prompt_template_str,
        "query_improvement": system_prompt_improvement_template_str,
        "guidelines": _get_chat_answer_guidelines_fr("ExampleParty"),
    }


def optimize_response_prompt(goldens: list, model, iterations: int = 3):
    """Optimize the main RAG response system prompt."""
    from deepeval.prompt import Prompt
    from deepeval.optimizer import PromptOptimizer
    from deepeval.optimizer.algorithms import GEPA
    from deepeval.metrics import FaithfulnessMetric, AnswerRelevancyMetric
    from deepeval.dataset import Golden

    prompts = _get_current_prompts()

    # Create a simplified version of the response prompt for optimization
    # We optimize the guidelines section since that's the instruction part
    guidelines_template = """## Directives pour ta réponse
1. **Basé sur les sources** — Réfère-toi exclusivement aux extraits de documents fournis. Si les documents ne contiennent pas l'information, dis-le honnêtement. N'invente jamais de faits.
2. **Neutralité stricte** — N'évalue pas les positions. Évite les jugements. Ne donne aucune recommandation de vote.
3. **Transparence** — Signale les incertitudes. Distingue faits et interprétations.
4. **Style** — Réponds en français, de manière sourcée et concise (1-3 phrases). Cite les sources entre crochets [id].
5. **Limites** — Signale quand les informations pourraient être obsolètes ou incomplètes.

Question de l'utilisateur : {input}"""

    prompt = Prompt(text_template=guidelines_template)

    # Model callback — simulates our RAG pipeline response
    async def model_callback(prompt_obj: Prompt, golden: Golden) -> str:
        """Run the prompt through Ollama and return the response."""
        interpolated = prompt_obj.interpolate(input=golden.input)

        # Use Ollama directly for the response
        import urllib.request
        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

        payload = json.dumps({
            "model": os.environ.get("OLLAMA_MODEL", "llama3.2"),
            "prompt": interpolated,
            "stream": False,
            "options": {"temperature": 0.1},
        }).encode()

        req = urllib.request.Request(
            f"{ollama_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            return result.get("response", "")

    # Metrics to optimize against
    metrics = [
        AnswerRelevancyMetric(threshold=0.5, model=model, include_reason=True),
    ]

    print(f"\nOptimizing response prompt with GEPA ({iterations} iterations)...")
    print(f"Using {len(goldens)} golden test cases and {len(metrics)} metrics")

    gepa = GEPA(
        iterations=iterations,
        pareto_size=min(3, len(goldens)),
        minibatch_size=min(5, len(goldens)),
    )

    optimizer = PromptOptimizer(
        algorithm=gepa,
        model_callback=model_callback,
        metrics=metrics,
    )

    optimized_prompt = optimizer.optimize(
        prompt=prompt,
        goldens=goldens[:15],  # Limit to avoid long runs with Ollama
    )

    return optimized_prompt


def optimize_query_improvement_prompt(goldens: list, model, iterations: int = 3):
    """Optimize the RAG query improvement prompt."""
    from deepeval.prompt import Prompt
    from deepeval.optimizer import PromptOptimizer
    from deepeval.optimizer.algorithms import GEPA
    from deepeval.metrics import AnswerRelevancyMetric
    from deepeval.dataset import Golden

    query_template = """Tu écris des requêtes optimisées pour un système RAG politique.

À partir du message de l'utilisateur, génère une requête de recherche qui:
- Recherche les informations mentionnées par l'utilisateur
- Ajoute des synonymes et formulations alternatives
- Inclut des détails pertinents non mentionnés par l'utilisateur

Message: {input}

Requête optimisée:"""

    prompt = Prompt(text_template=query_template)

    async def model_callback(prompt_obj: Prompt, golden: Golden) -> str:
        interpolated = prompt_obj.interpolate(input=golden.input)

        import urllib.request
        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

        payload = json.dumps({
            "model": os.environ.get("OLLAMA_MODEL", "llama3.2"),
            "prompt": interpolated,
            "stream": False,
            "options": {"temperature": 0.1},
        }).encode()

        req = urllib.request.Request(
            f"{ollama_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            return result.get("response", "")

    metrics = [
        AnswerRelevancyMetric(threshold=0.5, model=model, include_reason=True),
    ]

    print(f"\nOptimizing query improvement prompt with GEPA ({iterations} iterations)...")

    gepa = GEPA(
        iterations=iterations,
        pareto_size=min(3, len(goldens)),
        minibatch_size=min(5, len(goldens)),
    )

    optimizer = PromptOptimizer(
        algorithm=gepa,
        model_callback=model_callback,
        metrics=metrics,
    )

    optimized_prompt = optimizer.optimize(
        prompt=prompt,
        goldens=goldens[:10],
    )

    return optimized_prompt


def main():
    parser = argparse.ArgumentParser(description="Optimize RAG prompts using DeepEval GEPA")
    parser.add_argument(
        "--prompt",
        choices=["response", "query_improvement", "all"],
        default="all",
        help="Which prompt to optimize",
    )
    parser.add_argument("--iterations", type=int, default=3, help="GEPA iterations")
    args = parser.parse_args()

    print("Building Ollama judge model...")
    model = _build_ollama_model()

    goldens = _load_goldens()

    OPTIMIZED_DIR.mkdir(exist_ok=True)

    results = {}

    if args.prompt in ("response", "all"):
        try:
            optimized = optimize_response_prompt(goldens, model, args.iterations)
            results["response"] = {
                "optimized_template": optimized.text_template,
            }
            # Save optimized prompt
            out_file = OPTIMIZED_DIR / "response_prompt.txt"
            out_file.write_text(optimized.text_template)
            print(f"\nOptimized response prompt saved to: {out_file}")
            print(f"Template:\n{optimized.text_template[:500]}...")
        except Exception as e:
            print(f"Error optimizing response prompt: {e}")
            import traceback
            traceback.print_exc()

    if args.prompt in ("query_improvement", "all"):
        try:
            optimized = optimize_query_improvement_prompt(goldens, model, args.iterations)
            results["query_improvement"] = {
                "optimized_template": optimized.text_template,
            }
            out_file = OPTIMIZED_DIR / "query_improvement_prompt.txt"
            out_file.write_text(optimized.text_template)
            print(f"\nOptimized query improvement prompt saved to: {out_file}")
            print(f"Template:\n{optimized.text_template[:500]}...")
        except Exception as e:
            print(f"Error optimizing query improvement prompt: {e}")
            import traceback
            traceback.print_exc()

    # Save summary
    summary_path = OPTIMIZED_DIR / "optimization_summary.json"
    summary_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nOptimization summary saved to: {summary_path}")


if __name__ == "__main__":
    main()
