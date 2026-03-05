"""
Auto-generate golden test cases from crawled content using direct Ollama generation.

Reads markdown files from firebase/firestore_data/dev/crawled_content/,
chunks them with LangChain, and generates question/answer pairs in French
for RAG evaluation.

Usage:
    poetry run python scripts/generate_goldens.py
    poetry run python scripts/generate_goldens.py --max-per-doc 3 --output tests/eval/datasets/generated_goldens.json
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CRAWLED_CONTENT_DIR = (
    PROJECT_ROOT / "firebase" / "firestore_data" / "dev" / "crawled_content"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "tests" / "eval" / "datasets" / "generated_goldens.json"

# Patterns that indicate garbage output (meta-instructions, English leakage)
GARBAGE_PATTERNS = [
    r"\bI can\b", r"\bI'd be happy\b", r"\bI would\b", r"\bI am\b",
    r"\bHere is\b", r"\bHere are\b", r"\bAs an AI\b", r"\bAs a language model\b",
    r"\bSure,?\s", r"\bOf course\b", r"\bCertainly\b",
    r"\bPlease note\b", r"\bNote that\b", r"\bKeep in mind\b",
    r"\bIn this (context|document|text)\b",
]
GARBAGE_RE = re.compile("|".join(GARBAGE_PATTERNS), re.IGNORECASE)


def _check_ollama(url: str) -> None:
    """Verify Ollama is reachable."""
    try:
        urllib.request.urlopen(url, timeout=3)
    except Exception:
        print(f"ERROR: Ollama not reachable at {url}")
        print("Start Ollama with: ollama serve")
        sys.exit(1)


def _call_ollama(url: str, model: str, prompt: str) -> str:
    """Call Ollama generate endpoint and return the response text."""
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3},
    }).encode()

    req = urllib.request.Request(
        f"{url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode())
    return result.get("response", "")


def _is_french(text: str) -> bool:
    """Heuristic check that text is primarily French (not English)."""
    french_markers = [
        "le ", "la ", "les ", "des ", "du ", "un ", "une ",
        "est ", "sont ", "dans ", "pour ", "avec ", "sur ",
        "qui ", "que ", "ce ", "cette ", "nous ", "vous ",
        "politique", "parti", "programme", "proposition",
    ]
    text_lower = text.lower()
    hits = sum(1 for m in french_markers if m in text_lower)
    return hits >= 3


def _is_valid_golden(question: str, answer: str) -> bool:
    """Filter out garbage outputs."""
    if len(question) < 20 or len(answer) < 20:
        return False
    if GARBAGE_RE.search(question) or GARBAGE_RE.search(answer):
        return False
    if not _is_french(question) or not _is_french(answer):
        return False
    return True


def _extract_json_array(text: str) -> list[dict]:
    """Extract a JSON array from LLM response text, handling common issues."""
    text = text.strip()

    # Try direct parse
    if text.startswith("["):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # Try to extract from markdown code block
    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find any JSON array in the text
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return []


def _collect_markdown_files(content_dir: Path, entity_type: str | None = None) -> list[dict]:
    """Collect markdown files with metadata from crawled content directory."""
    results = []
    search_dirs = []

    if entity_type:
        search_dirs.append(content_dir / entity_type)
    else:
        search_dirs.extend([content_dir / "parties", content_dir / "candidates"])

    skip_names = {"mentions-legales", "politique-de-confidentialite", "cgu", "mentions",
                  "copie-de-mentions-legales", "desabonnement-des-listes-de-diffusion",
                  "informations-juridiques", "presse", "contacts-presse", "kit-graphique",
                  "charte-graphique"}

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for md_file in sorted(search_dir.rglob("*.md")):
            content = md_file.read_text(errors="ignore").strip()
            if len(content) < 200:
                continue
            if md_file.stem in skip_names:
                continue

            info = _extract_entity_info(str(md_file))
            results.append({
                "path": str(md_file),
                "content": content,
                "name": md_file.stem,
                **info,
            })

    return results


def _extract_entity_info(filepath: str) -> dict:
    """Extract party/candidate ID and type from file path."""
    path = Path(filepath)
    parts = path.parts

    try:
        cc_idx = parts.index("crawled_content")
        entity_type = parts[cc_idx + 1]
        entity_id = parts[cc_idx + 2]
        return {"entity_type": entity_type, "entity_id": entity_id}
    except (ValueError, IndexError):
        return {"entity_type": "unknown", "entity_id": "unknown"}


def _chunk_documents(docs: list[dict], chunk_size: int = 800, chunk_overlap: int = 100) -> list[dict]:
    """Chunk documents into context groups using LangChain splitter.

    Returns list of dicts with 'context' (joined chunks) and 'source' metadata.
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    contexts = []
    for doc in docs:
        chunks = splitter.split_text(doc["content"])
        if not chunks:
            continue

        source = f"{doc['entity_type']}/{doc['entity_id']} — {doc['name']}"

        # Group chunks into contexts of 2-3 related chunks
        for i in range(0, len(chunks), 2):
            context_group = chunks[i:i + 3]
            if context_group:
                contexts.append({
                    "context": "\n\n".join(context_group),
                    "source": source,
                })

    return contexts


def generate_goldens(
    max_per_context: int = 2,
    max_docs: int = 20,
    output_path: Path = DEFAULT_OUTPUT,
    entity_type: str | None = None,
):
    """Generate golden test cases from crawled documents using direct Ollama calls."""
    start_time = time.time()

    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.2")

    print(f"Using Ollama at {ollama_url} with model {ollama_model}")
    _check_ollama(ollama_url)

    print(f"Collecting markdown files from {CRAWLED_CONTENT_DIR}...")
    docs = _collect_markdown_files(CRAWLED_CONTENT_DIR, entity_type)

    if not docs:
        print("ERROR: No markdown files found in crawled content directory.")
        print(f"Expected at: {CRAWLED_CONTENT_DIR}")
        sys.exit(1)

    # Limit and prioritize documents
    if len(docs) > max_docs:
        priority_stems = {"programme", "projet", "index", "nos-valeurs", "les-urgences",
                          "engagements", "pacte-lyonnais", "lyon-de-demain",
                          "nos-ambitions-municipales", "notre-programme", "notre-projet"}
        priority = [d for d in docs if d["name"] in priority_stems]
        rest = [d for d in docs if d not in priority]
        docs = (priority + rest)[:max_docs]

    print(f"Using {len(docs)} documents for golden generation:")
    for d in docs:
        print(f"  - [{d['entity_type']}/{d['entity_id']}] {d['name']}.md ({len(d['content'])} chars)")

    # Chunk documents
    print("\nChunking documents...")
    contexts = _chunk_documents(docs)
    print(f"Created {len(contexts)} context groups from {len(docs)} documents")

    # Limit contexts to keep generation time reasonable
    max_contexts = max_docs * 3
    if len(contexts) > max_contexts:
        contexts = contexts[:max_contexts]
        print(f"Limited to {max_contexts} contexts")

    # Generate goldens via direct Ollama calls
    print(f"\nGenerating goldens from {len(contexts)} contexts...")
    goldens = []
    failed = 0

    for i, ctx in enumerate(contexts):
        prompt = (
            "Tu es un expert en politique française. "
            "À partir de cet extrait d'un document politique français, "
            f"génère exactement {max_per_context} paires question/réponse EN FRANÇAIS.\n\n"
            "Règles :\n"
            "- Les questions doivent être celles qu'un citoyen français poserait naturellement\n"
            "- Les réponses doivent être factuelles et basées uniquement sur l'extrait\n"
            "- Tout doit être en français, JAMAIS en anglais\n"
            "- Pas de méta-commentaires (pas de « voici », « je vais », etc.)\n\n"
            f"Extrait :\n{ctx['context']}\n\n"
            "Réponds UNIQUEMENT avec un tableau JSON, sans texte avant ou après :\n"
            '[{"question": "...", "answer": "..."}]'
        )

        try:
            response_text = _call_ollama(ollama_url, ollama_model, prompt)
            pairs = _extract_json_array(response_text)

            new_count = 0
            for pair in pairs:
                q = pair.get("question", "").strip()
                a = pair.get("answer", "").strip()
                if _is_valid_golden(q, a):
                    goldens.append({
                        "input": q,
                        "expected_output": a,
                        "retrieval_context": [ctx["context"]],
                        "source": f"[Source: {ctx['source']}]",
                    })
                    new_count += 1

            print(f"  [{i+1}/{len(contexts)}] {ctx['source'][:50]}... → {new_count} valid pairs")

        except Exception as e:
            failed += 1
            print(f"  [{i+1}/{len(contexts)}] ERROR: {e}")

    elapsed = time.time() - start_time

    # Build output
    result = {
        "generated": goldens,
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "source_docs": len(docs),
            "total_contexts": len(contexts),
            "total_goldens": len(goldens),
            "failed_contexts": failed,
            "model": ollama_model,
            "elapsed_s": round(elapsed, 1),
            "docs_used": [
                {"entity_type": d["entity_type"], "entity_id": d["entity_id"], "name": d["name"]}
                for d in docs
            ],
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    print(f"\nGenerated {len(goldens)} golden test cases in {elapsed:.0f}s ({failed} context failures)")
    print(f"Saved to: {output_path}")

    # Show samples
    for i, g in enumerate(goldens[:3]):
        print(f"\n--- Sample {i+1} ---")
        print(f"Q: {g['input']}")
        print(f"A: {g['expected_output'][:150]}...")


def main():
    parser = argparse.ArgumentParser(description="Generate golden test cases from crawled content")
    parser.add_argument("--max-per-context", type=int, default=2, help="Max goldens per context group")
    parser.add_argument("--max-docs", type=int, default=20, help="Max documents to process")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT), help="Output JSON path")
    parser.add_argument("--type", choices=["parties", "candidates"], help="Filter by entity type")
    args = parser.parse_args()

    generate_goldens(
        max_per_context=args.max_per_context,
        max_docs=args.max_docs,
        output_path=Path(args.output),
        entity_type=args.type,
    )


if __name__ == "__main__":
    main()
