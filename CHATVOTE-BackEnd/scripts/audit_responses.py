#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""
Audit response coherence by running test questions through the RAG pipeline.

Usage:
    cd CHATVOTE-BackEnd
    poetry run python scripts/audit_responses.py

Requirements: backend services must be running (Qdrant :6333, Ollama :11434, Firestore :8081)
"""
import asyncio
import sys
import os
import time
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load env before importing backend modules
from src.utils import load_env
load_env()

from src.chatbot_async import (
    generate_improvement_rag_query,
    generate_streaming_chatbot_response,
    get_rag_context,
)
from src.vector_store_helper import identify_relevant_docs_with_llm_based_reranking
from src.firebase_service import aget_parties
from src.models.general import LLMSize

# 10 test questions across key political domains
TEST_QUESTIONS = [
    ("Quelles sont les propositions pour les transports ?", "place-publique"),
    ("Que proposent les partis pour l'écologie et le climat ?", "europe-ecologie-les-verts"),
    ("Quelle est la position sur l'immigration ?", "reconquete"),
    ("Quelle est la position sur l'immigration ?", "la-france-insoumise"),
    ("Comment améliorer le pouvoir d'achat des ménages ?", "place-publique"),
    ("Quelles réformes pour l'éducation nationale ?", "reconquete"),
    ("Quelle politique énergétique pour la France ?", "europe-ecologie-les-verts"),
    ("Comment réduire le chômage ?", "la-france-insoumise"),
    ("Que proposent-ils pour le système de santé ?", "place-publique"),
    ("Quelle vision pour l'Europe et la souveraineté ?", "renaissance"),
]

# 3 questions for full LLM pipeline (slow - uses Ollama)
FULL_PIPELINE_QUESTIONS = [
    ("Que proposent les partis pour l'écologie et le climat ?", "europe-ecologie-les-verts"),
    ("Comment améliorer le pouvoir d'achat des ménages ?", "place-publique"),
    ("Quelle est la position sur l'immigration ?", "la-france-insoumise"),
]


async def run_rag_audit(question: str, party_id: str, party_map: dict) -> dict:
    """Run RAG retrieval only (fast path)."""
    party = party_map.get(party_id)
    if party is None:
        return {"question": question, "party_id": party_id, "error": "party not found"}

    t0 = time.perf_counter()

    # Step 1: use question as-is (skip LLM query improvement to stay within time budget)
    improved_query = question
    query_error = None
    t1 = time.perf_counter()

    # Step 2: retrieve docs (no LLM reranking to stay fast)
    from src.vector_store_helper import identify_relevant_docs
    try:
        docs = await identify_relevant_docs(
            party=party,
            rag_query=improved_query,
            n_docs=5,
            score_threshold=0.5,
        )
    except Exception as e:
        docs = []
        retrieval_error = str(e)
    else:
        retrieval_error = None

    t2 = time.perf_counter()

    # Assess doc quality
    doc_summaries = []
    for doc in docs[:5]:
        meta = doc.metadata
        doc_summaries.append({
            "source_doc": meta.get("source_document", "unknown"),
            "page": meta.get("page"),
            "url": meta.get("url", "")[:80],
            "preview": doc.page_content[:100].replace("\n", " "),
        })

    return {
        "question": question,
        "party_id": party_id,
        "improved_query": improved_query[:120] if improved_query else None,
        "query_error": query_error,
        "n_docs": len(docs),
        "retrieval_error": retrieval_error,
        "docs": doc_summaries,
        "query_ms": round((t1 - t0) * 1000),
        "retrieval_ms": round((t2 - t1) * 1000),
    }


async def run_full_pipeline(question: str, party_id: str, party_map: dict, all_parties: list) -> dict:
    """Run the full pipeline: query improvement → retrieval → LLM streaming response."""
    party = party_map.get(party_id)
    if party is None:
        return {"question": question, "party_id": party_id, "error": "party not found"}

    t0 = time.perf_counter()

    # Step 1: improve query
    try:
        improved_query = await generate_improvement_rag_query(
            responder=party,
            conversation_history="",
            last_user_message=question,
        )
    except Exception as e:
        return {"question": question, "party_id": party_id, "error": f"query improvement failed: {e}"}

    t1 = time.perf_counter()

    # Step 2: retrieve docs
    try:
        docs = await identify_relevant_docs_with_llm_based_reranking(
            responder=party,
            rag_query=improved_query,
            chat_history="",
            user_message=question,
            n_docs=10,
            score_threshold=0.5,
        )
    except Exception as e:
        return {"question": question, "party_id": party_id, "error": f"retrieval failed: {e}"}

    t2 = time.perf_counter()

    # Step 3: generate streaming response (collect chunks)
    try:
        stream = await generate_streaming_chatbot_response(
            responder=party,
            conversation_history="",
            user_message=question,
            relevant_docs=docs,
            all_parties=all_parties,
            chat_response_llm_size=LLMSize.SMALL,
            use_premium_llms=False,
            locale="fr",
        )
        chunks = []
        async for chunk in stream:
            if hasattr(chunk, "content") and chunk.content:
                chunks.append(chunk.content)
        response_text = "".join(chunks)
    except Exception as e:
        return {"question": question, "party_id": party_id, "error": f"LLM generation failed: {e}"}

    t3 = time.perf_counter()

    # Check quality
    sources_cited = any(
        kw in response_text
        for kw in ["source", "programme", "manifeste", "selon", "d'après", "propose", "prévoit"]
    )
    has_content = len(response_text) > 100

    return {
        "question": question,
        "party_id": party_id,
        "improved_query": improved_query[:120],
        "n_docs": len(docs),
        "response_preview": response_text[:400],
        "response_length": len(response_text),
        "sources_cited": sources_cited,
        "has_content": has_content,
        "query_ms": round((t1 - t0) * 1000),
        "retrieval_ms": round((t2 - t1) * 1000),
        "llm_ms": round((t3 - t2) * 1000),
        "total_ms": round((t3 - t0) * 1000),
    }


async def main():
    print("Loading parties from Firestore emulator...")
    all_parties = await aget_parties()
    party_map = {p.party_id: p for p in all_parties}
    print(f"Loaded {len(all_parties)} parties: {[p.party_id for p in all_parties]}\n")

    # --- RAG audit (all 10 questions) ---
    print("=" * 60)
    print("RAG RETRIEVAL AUDIT (10 questions)")
    print("=" * 60)
    rag_results = []
    for question, party_id in TEST_QUESTIONS:
        print(f"\n[{party_id}] {question}")
        result = await run_rag_audit(question, party_id, party_map)
        rag_results.append(result)
        if result.get("error"):
            print(f"  ERROR: {result['error']}")
        else:
            print(f"  improved_query: {result['improved_query']}")
            print(f"  n_docs={result['n_docs']}  query={result['query_ms']}ms  retrieval={result['retrieval_ms']}ms")
            for i, doc in enumerate(result["docs"][:3]):
                print(f"  doc[{i}] src={doc['source_doc']} pg={doc['page']} | {doc['preview']}")

    # --- Full pipeline (3 questions) ---
    print("\n" + "=" * 60)
    print("FULL LLM PIPELINE AUDIT (3 questions, slow)")
    print("=" * 60)
    pipeline_results = []
    for question, party_id in FULL_PIPELINE_QUESTIONS:
        print(f"\n[{party_id}] {question}")
        print("  Running full pipeline (may take 30-60s)...")
        result = await run_full_pipeline(question, party_id, party_map, all_parties)
        pipeline_results.append(result)
        if result.get("error"):
            print(f"  ERROR: {result['error']}")
        else:
            print(f"  n_docs={result['n_docs']}  total={result['total_ms']}ms (query={result['query_ms']}ms retrieval={result['retrieval_ms']}ms llm={result['llm_ms']}ms)")
            print(f"  has_content={result['has_content']}  sources_cited={result['sources_cited']}")
            print(f"  RESPONSE: {result['response_preview'][:300]}")

    # Write JSON results for report
    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "..", ".omc", "reports", "audit_raw_results.json"
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"rag_results": rag_results, "pipeline_results": pipeline_results}, f, ensure_ascii=False, indent=2)
    print(f"\nRaw results written to {output_path}")

    return rag_results, pipeline_results


if __name__ == "__main__":
    results = asyncio.run(main())
