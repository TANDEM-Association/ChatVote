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
        gemini_model = os.environ.get("DEEPEVAL_GEMINI_MODEL", GEMINI_2_FLASH)
        return GeminiModel(
            model=gemini_model,
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


# ---------------------------------------------------------------------------
# Auto-save eval results after each test session for report generation
# ---------------------------------------------------------------------------

_eval_results = []


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_logreport(report):
    """Capture test results including DeepEval metric data."""
    if report.when != "call":
        return

    result = {
        "name": report.nodeid.split("::")[-1],
        "nodeid": report.nodeid,
        "passed": report.passed,
        "duration": report.duration,
    }

    # Extract DeepEval assertion details from the failure message
    if report.failed and report.longreprtext:
        result["error"] = report.longreprtext[:500]

    _eval_results.append(result)


def pytest_sessionfinish(session, exitstatus):
    """Save collected test results to reports/cache/ for report generation without re-running."""
    import json
    from datetime import datetime

    if not _eval_results:
        return

    cache_dir = PROJECT_ROOT / "reports" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Determine test file(s) involved
    test_files = set()
    for r in _eval_results:
        parts = r["nodeid"].split("::")
        if parts:
            test_files.add(parts[0])

    data = {
        "timestamp": datetime.now().isoformat(),
        "test_files": list(test_files),
        "total": len(_eval_results),
        "passed": sum(1 for r in _eval_results if r["passed"]),
        "failed": sum(1 for r in _eval_results if not r["passed"]),
        "results": _eval_results,
    }

    # Save as latest results (overwritten each run)
    dest = cache_dir / "latest_results.json"
    dest.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    # Also save timestamped copy
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    history_dest = cache_dir / f"results_{ts}.json"
    history_dest.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    # Auto-generate HTML report from cached results
    try:
        _auto_generate_report()
    except Exception as e:
        print(f"Warning: Could not auto-generate HTML report: {e}")


def _auto_generate_report():
    """Run eval_report.py --from-cache to regenerate the HTML report."""
    import subprocess

    report_script = PROJECT_ROOT / "scripts" / "eval_report.py"
    if not report_script.exists():
        return

    report_output = PROJECT_ROOT / "reports" / "eval_report.html"
    subprocess.run(
        [
            sys.executable, str(report_script),
            "--mode", "all",
            "--from-cache",
            "--output", str(report_output),
        ],
        cwd=str(PROJECT_ROOT),
        timeout=30,
        capture_output=True,
    )
    print(f"HTML report updated: {report_output}")
