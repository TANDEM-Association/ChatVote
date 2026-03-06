"""
Shared fixtures for all test suites (eval + red_team).

Provides the LLM judge model used by DeepEval metrics.
Uses Ollama locally by default (no API keys needed).
Set DEEPEVAL_JUDGE=gemini to use Google Gemini instead.
"""

import os
import sys
from pathlib import Path

import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.model_config import (
    GEMINI_2_FLASH,
    OLLAMA_CHAT_MODEL,
)


def _build_judge():
    """Build the LLM judge model based on environment config."""
    judge_type = os.environ.get("DEEPEVAL_JUDGE", "ollama").lower()

    if judge_type == "gemini":
        from deepeval.models import GeminiModel
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key or api_key.startswith("your_"):
            return None, "GOOGLE_API_KEY not set"
        return GeminiModel(
            model=GEMINI_2_FLASH,
            api_key=api_key,
            temperature=0.0,
        ), None
    else:
        # Default: Ollama (zero API keys)
        from deepeval.models import OllamaModel
        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

        # Check Ollama is reachable
        try:
            import urllib.request
            urllib.request.urlopen(ollama_url, timeout=2)
        except Exception:
            return None, f"Ollama not reachable at {ollama_url}"

        # Allow override for judge model (e.g. use lighter model for faster evals)
        judge_model_name = os.environ.get("DEEPEVAL_OLLAMA_MODEL", OLLAMA_CHAT_MODEL)

        return OllamaModel(
            model=judge_model_name,
            base_url=ollama_url,
            temperature=0.0,
        ), None


@pytest.fixture(scope="session")
def judge_model():
    """LLM judge model for evaluation metrics (Ollama by default)."""
    model, error = _build_judge()
    if model is None:
        pytest.skip(error)
    return model


# Backward-compat alias used by red_team tests
@pytest.fixture(scope="session")
def gemini_judge(judge_model):
    return judge_model
