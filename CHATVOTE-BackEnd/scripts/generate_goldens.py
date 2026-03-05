"""
Auto-generate golden test cases from crawled content using DeepEval Synthesizer.

Reads markdown files from firebase/firestore_data/dev/crawled_content/
and generates question/answer pairs suitable for RAG evaluation.

Usage:
    poetry run python scripts/generate_goldens.py
    poetry run python scripts/generate_goldens.py --max-per-doc 3 --output tests/eval/datasets/generated_goldens.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CRAWLED_CONTENT_DIR = (
    PROJECT_ROOT / "firebase" / "firestore_data" / "dev" / "crawled_content"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "tests" / "eval" / "datasets" / "generated_goldens.json"


def _build_ollama_model():
    """Build OllamaModel for the synthesizer."""
    from deepeval.models import OllamaModel

    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.2")

    # Check Ollama is reachable
    try:
        import urllib.request
        urllib.request.urlopen(ollama_url, timeout=3)
    except Exception:
        print(f"ERROR: Ollama not reachable at {ollama_url}")
        print("Start Ollama with: ollama serve")
        sys.exit(1)

    return OllamaModel(model=ollama_model, base_url=ollama_url, temperature=0.0)


def _collect_markdown_files(content_dir: Path, entity_type: str | None = None) -> list[str]:
    """Collect markdown file paths from crawled content directory.

    Args:
        content_dir: Root crawled_content directory
        entity_type: Optional filter — "parties" or "candidates"
    """
    md_files = []
    search_dirs = []

    if entity_type:
        search_dirs.append(content_dir / entity_type)
    else:
        search_dirs.extend([content_dir / "parties", content_dir / "candidates"])

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for md_file in sorted(search_dir.rglob("*.md")):
            # Skip tiny files (< 200 chars) and legal/privacy pages
            content = md_file.read_text(errors="ignore")
            if len(content) < 200:
                continue
            skip_names = {"mentions-legales", "politique-de-confidentialite", "cgu", "mentions"}
            if md_file.stem in skip_names:
                continue
            md_files.append(str(md_file))

    return md_files


def _extract_entity_info(filepath: str) -> dict:
    """Extract party/candidate ID and type from file path."""
    path = Path(filepath)
    parts = path.parts

    # Find the entity type and ID from path
    # e.g., .../crawled_content/parties/renaissance/markdown/index.md
    try:
        cc_idx = parts.index("crawled_content")
        entity_type = parts[cc_idx + 1]  # "parties" or "candidates"
        entity_id = parts[cc_idx + 2]    # e.g., "renaissance"
        return {"entity_type": entity_type, "entity_id": entity_id}
    except (ValueError, IndexError):
        return {"entity_type": "unknown", "entity_id": "unknown"}


def generate_goldens(
    max_per_doc: int = 2,
    max_docs: int = 20,
    output_path: Path = DEFAULT_OUTPUT,
    entity_type: str | None = None,
):
    """Generate golden test cases from crawled documents."""
    from deepeval.synthesizer import Synthesizer
    from deepeval.synthesizer.config import (
        ContextConstructionConfig,
        EvolutionConfig,
        FiltrationConfig,
    )
    from deepeval.synthesizer.types import Evolution

    print("Building Ollama model for synthesis...")
    model = _build_ollama_model()

    print(f"Collecting markdown files from {CRAWLED_CONTENT_DIR}...")
    md_files = _collect_markdown_files(CRAWLED_CONTENT_DIR, entity_type)

    if not md_files:
        print("ERROR: No markdown files found in crawled content directory.")
        print(f"Expected at: {CRAWLED_CONTENT_DIR}")
        sys.exit(1)

    # Limit documents to process
    if len(md_files) > max_docs:
        # Prefer programme/projet/index files
        priority_stems = {"programme", "projet", "index", "nos-valeurs", "les-urgences",
                          "engagements", "pacte-lyonnais", "lyon-de-demain", "nos-ambitions-municipales"}
        priority = [f for f in md_files if Path(f).stem in priority_stems]
        rest = [f for f in md_files if f not in priority]
        md_files = (priority + rest)[:max_docs]

    print(f"Using {len(md_files)} documents for golden generation:")
    for f in md_files:
        info = _extract_entity_info(f)
        print(f"  - [{info['entity_type']}/{info['entity_id']}] {Path(f).name}")

    # Configure synthesizer for political Q&A
    context_config = ContextConstructionConfig(
        chunk_size=800,
        chunk_overlap=100,
        max_contexts_per_document=3,
        min_contexts_per_document=1,
        context_quality_threshold=0.3,  # Lower for Ollama
    )

    evolution_config = EvolutionConfig(
        num_evolutions=1,
        evolutions={
            Evolution.REASONING: 0.3,      # "Why does X propose Y?"
            Evolution.COMPARATIVE: 0.3,    # "Compare X and Y positions"
            Evolution.CONCRETIZING: 0.2,   # "Give specific examples"
            Evolution.IN_BREADTH: 0.2,     # Broader topic coverage
        },
    )

    filtration_config = FiltrationConfig(
        synthetic_input_quality_threshold=0.3,  # Lower for Ollama
        max_quality_retries=2,
        critic_model=model,
    )

    print("\nInitializing synthesizer...")
    synthesizer = Synthesizer(
        model=model,
        async_mode=False,
        evolution_config=evolution_config,
        filtration_config=filtration_config,
    )

    print("Generating goldens (this may take a while with Ollama)...")
    try:
        goldens = synthesizer.generate_goldens_from_docs(
            document_paths=md_files,
            max_goldens_per_context=max_per_doc,
            include_expected_output=True,
            context_construction_config=context_config,
        )
    except Exception as e:
        print(f"Error during generation: {e}")
        print("Trying with fewer documents...")
        md_files = md_files[:5]
        goldens = synthesizer.generate_goldens_from_docs(
            document_paths=md_files,
            max_goldens_per_context=max_per_doc,
            include_expected_output=True,
            context_construction_config=context_config,
        )

    # Convert to our test format
    result = {
        "generated": [],
        "metadata": {
            "source_docs": len(md_files),
            "total_goldens": len(goldens),
            "model": os.environ.get("OLLAMA_MODEL", "llama3.2"),
        },
    }

    for golden in goldens:
        entry = {
            "input": golden.input,
            "expected_output": golden.expected_output or "",
            "retrieval_context": golden.context or [],
        }
        result["generated"].append(entry)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    print(f"\nGenerated {len(goldens)} golden test cases")
    print(f"Saved to: {output_path}")

    # Show samples
    for i, g in enumerate(goldens[:3]):
        print(f"\n--- Sample {i+1} ---")
        print(f"Q: {g.input}")
        print(f"A: {(g.expected_output or '')[:150]}...")


def main():
    parser = argparse.ArgumentParser(description="Generate golden test cases from crawled content")
    parser.add_argument("--max-per-doc", type=int, default=2, help="Max goldens per document context")
    parser.add_argument("--max-docs", type=int, default=20, help="Max documents to process")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT), help="Output JSON path")
    parser.add_argument("--type", choices=["parties", "candidates"], help="Filter by entity type")
    args = parser.parse_args()

    generate_goldens(
        max_per_doc=args.max_per_doc,
        max_docs=args.max_docs,
        output_path=Path(args.output),
        entity_type=args.type,
    )


if __name__ == "__main__":
    main()
