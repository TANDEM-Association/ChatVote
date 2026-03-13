# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""
Central model registry — the single source of truth for all LLM and embedding
model identifiers, dimensions, and provider metadata used across the codebase.

Every file that needs a model name or embedding dimension MUST import from here.
"""

import os

# ---------------------------------------------------------------------------
# Chat / Generation models
# ---------------------------------------------------------------------------

# Google
GEMINI_2_FLASH = "gemini-2.5-flash"

# OpenAI
GPT_4O = "gpt-4o-2024-08-06"
GPT_4O_MINI = "gpt-4o-mini"

# Azure (same underlying models, but deployment names can differ)
AZURE_GPT_4O_DEPLOYMENT = "gpt-4o-2024-08-06"
AZURE_GPT_4O_MINI_DEPLOYMENT = "gpt-4o-mini-2024-07-18"

# Anthropic
CLAUDE_SONNET = "claude-sonnet-4-5-20250929"
CLAUDE_HAIKU = "claude-haiku-4-5-20251001"

# Ollama (local)
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

# ---------------------------------------------------------------------------
# Embedding models
# ---------------------------------------------------------------------------

# Google
GOOGLE_EMBED_MODEL = "models/gemini-embedding-001"
GOOGLE_EMBED_DIM = 3072

# Scaleway (OpenAI-compatible endpoint)
SCALEWAY_EMBED_MODEL = os.getenv("SCALEWAY_EMBED_MODEL", "qwen3-embedding-8b")
SCALEWAY_EMBED_DIM = int(os.getenv("SCALEWAY_EMBED_DIM", "4096"))
SCALEWAY_EMBED_DEFAULT_URL = "https://api.scaleway.ai/v1"

# OpenAI
OPENAI_EMBED_MODEL = "text-embedding-3-large"
OPENAI_EMBED_DIM = 3072

# Ollama (local)
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_EMBED_DIM = int(os.getenv("OLLAMA_EMBED_DIM", "768"))

# ---------------------------------------------------------------------------
# Capacity estimates (requests per minute per user)
# ---------------------------------------------------------------------------

CAPACITY_GEMINI_2_FLASH = 108
CAPACITY_GPT_4O_OPENAI_TIER_5 = 3759
CAPACITY_GPT_4O_AZURE = 112
CAPACITY_GPT_4O_MINI_OPENAI_TIER_5 = 4054
CAPACITY_GPT_4O_MINI_AZURE = 108
CAPACITY_CLAUDE_SONNET = 50
CAPACITY_CLAUDE_HAIKU = 100
