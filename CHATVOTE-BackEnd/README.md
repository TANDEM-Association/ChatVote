<!--
SPDX-FileCopyrightText: 2025 chatvote

SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
-->

# ChatVote Backend

A real-time political information chatbot backend for French municipal elections, powered by RAG (Retrieval-Augmented Generation) and multiple LLM providers.

## About ChatVote

- **Website**: https://chatvote.fr/
- **About Page**: https://chatvote.fr/about-us

ChatVote enables citizens to engage with political parties' positions in a modern, interactive way. Users can ask questions about electoral programs, compare party positions, and receive sourced answers from official documents and candidate websites.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [Testing](#testing)
- [Firebase Management](#firebase-management)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [License](#license)

---

## Features

### Core Capabilities

- **Multi-LLM Support**: Automatic failover across OpenAI, Azure OpenAI, Google Gemini, and Anthropic Claude
- **Real-time Streaming**: WebSocket-based streaming responses via Socket.IO
- **RAG Pipeline**: Vector search with LLM-based reranking for accurate document retrieval
- **Multi-scope Search**: National and local (municipality-level) search capabilities
- **Answer Caching**: Intelligent caching of responses for proposed questions
- **Internationalization**: Full support for French and English locales

### Chat Features

- **Party Chat**: Direct conversations with political party programs
- **Party Comparison**: Side-by-side comparison of multiple parties' positions
- **Candidate Information**: Local candidate website scraping and indexing
- **Voting Behavior**: Parliamentary voting history analysis and summaries
- **Pro/Con Perspectives**: External fact-checking via Perplexity AI
- **Smart Quick Replies**: AI-generated follow-up question suggestions

### Data Pipeline

- **Automatic Manifesto Indexing**: Firestore listeners trigger re-indexing on document updates
- **Website Scraping**: Playwright-based scraping of candidate campaign websites
- **PDF Processing**: Firebase Functions for automatic PDF ingestion into vector store
- **Scheduled Tasks**: Daily re-indexing of candidate websites and weekly municipality sync

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT APPLICATIONS                             │
│                    (Web App / Embed Widget / Mobile)                        │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AIOHTTP APPLICATION                               │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │   REST API      │  │   Socket.IO     │  │      Background Tasks       │  │
│  │  /api/v1/*      │  │   WebSocket     │  │  • Firestore Listeners      │  │
│  │  • Health       │  │  • Chat         │  │  • Scheduler (APScheduler)  │  │
│  │  • Admin        │  │  • Streaming    │  │  • Automatic Indexation     │  │
│  │  • Parliamentary│  │  • Events       │  │                             │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   LLM Providers │  │     Qdrant      │  │    Firebase     │
│  • OpenAI       │  │  Vector Store   │  │  • Firestore    │
│  • Azure OpenAI │  │  • Manifestos   │  │  • Storage      │
│  • Google Gemini│  │  • Candidates   │  │  • Functions    │
│  • Anthropic    │  │  • Voting Data  │  │                 │
│  • Perplexity   │  │                 │  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

### Component Overview

| Component         | Technology                  | Purpose                       |
| ----------------- | --------------------------- | ----------------------------- |
| HTTP Server       | aiohttp                     | REST API endpoints            |
| Real-time         | python-socketio             | WebSocket streaming           |
| Vector DB         | Qdrant                      | Similarity search for RAG     |
| Database          | Firebase Firestore          | Application data & caching    |
| Storage           | Firebase Storage            | PDF documents                 |
| Functions         | Firebase Functions (Python) | PDF ingestion pipeline        |
| LLM Orchestration | LangChain                   | Multi-provider LLM management |
| Scraping          | Playwright                  | Candidate website indexing    |
| Scheduling        | APScheduler                 | Periodic background tasks     |

---

## Tech Stack

### Languages & Runtimes

- **Python** 3.11-3.12
- **Poetry** for dependency management

### Core Dependencies

| Category       | Libraries                                                                        |
| -------------- | -------------------------------------------------------------------------------- |
| Web Framework  | `aiohttp`, `aiohttp-cors`, `aiohttp-pydantic`                                    |
| Real-time      | `python-socketio`                                                                |
| Validation     | `pydantic`                                                                       |
| LLM            | `langchain`, `langchain-openai`, `langchain-google-genai`, `langchain-anthropic` |
| Vector Store   | `qdrant-client`, `langchain-qdrant`                                              |
| Firebase       | `firebase-admin`                                                                 |
| Web Scraping   | `playwright`, `beautifulsoup4`                                                   |
| PDF Processing | `pypdf`                                                                          |
| Scheduling     | `apscheduler`                                                                    |
| Embeddings     | `text-embedding-3-large` (OpenAI) or `gemini-embedding-001` (Google)             |

### Supported LLM Providers

| Provider      | Models                                        | Use Case                                     |
| ------------- | --------------------------------------------- | -------------------------------------------- |
| Google Gemini | `gemini-2.0-flash`                            | Primary (high priority, supports both sizes) |
| OpenAI        | `gpt-4o`, `gpt-4o-mini`                       | Fallback                                     |
| Azure OpenAI  | `gpt-4o-2024-08-06`, `gpt-4o-mini-2024-07-18` | Enterprise fallback                          |
| Anthropic     | `claude-sonnet-4-5`, `claude-haiku-4-5`       | Alternative provider                         |
| Perplexity    | `sonar`, `sonar-pro`                          | Pro/Con fact-checking                        |

---

## Getting Started

### Prerequisites

- Python 3.11 or 3.12
- [Poetry](https://python-poetry.org/docs/#installing-with-the-official-installer)
- Access to at least one LLM provider (Google, OpenAI, Azure, or Anthropic)
- Qdrant instance (local or cloud)
- Firebase project (for Firestore and Storage)

### Installation

1. **Clone the repository**:

   ```bash
   git clone https://github.com/your-org/CHATVOTE-BackEnd.git
   cd CHATVOTE-BackEnd
   ```

2. **Install dependencies**:

   ```bash
   poetry install
   # With dev dependencies:
   poetry install --with dev
   ```

3. **Install pre-commit hooks** (recommended):

   ```bash
   poetry run pre-commit install
   ```

4. **Install Playwright browsers** (for candidate website scraping):
   ```bash
   poetry run playwright install chromium
   ```

---

## Configuration

### Environment Variables

Create a `.env` file based on `.env.example`:

```bash
cp .env.example .env
```

#### Required Variables

| Variable         | Description                                         |
| ---------------- | --------------------------------------------------- |
| `API_NAME`       | Must be `chatvote-api` (validation guard)           |
| `ENV`            | Environment: `dev` or `prod`                        |
| `QDRANT_URL`     | Qdrant instance URL (e.g., `http://localhost:6333`) |
| `QDRANT_API_KEY` | Qdrant API key (optional for local)                 |

#### LLM Provider Keys (at least one required)

| Variable                | Provider                         |
| ----------------------- | -------------------------------- |
| `GOOGLE_API_KEY`        | Google Gemini                    |
| `OPENAI_API_KEY`        | OpenAI                           |
| `AZURE_OPENAI_API_KEY`  | Azure OpenAI                     |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint            |
| `OPENAI_API_VERSION`    | Azure API version                |
| `ANTHROPIC_API_KEY`     | Anthropic Claude                 |
| `PERPLEXITY_API_KEY`    | Perplexity (for Pro/Con feature) |

#### Optional Variables

| Variable               | Description                               |
| ---------------------- | ----------------------------------------- |
| `LANGCHAIN_TRACING_V2` | Enable LangSmith tracing (`true`/`false`) |
| `LANGCHAIN_API_KEY`    | LangSmith API key                         |
| `LANGCHAIN_PROJECT`    | LangSmith project name                    |

### Firebase Credentials

#### Option 1: Application Default Credentials (Recommended for Development)

```bash
gcloud auth application-default login
gcloud config set project chatvote-dev
```

#### Option 2: Service Account JSON

Place the service account file in the project root:

- **Dev**: `chatvote-dev-firebase-adminsdk.json`
- **Prod**: `chatvote-firebase-adminsdk.json`

---

## Running the Application

### Local Development

```bash
poetry run python -m src.aiohttp_app --debug
```

The server starts at `http://localhost:8080`.

### Docker

#### Using Docker Compose (Recommended)

```bash
# Start Qdrant and the API
docker-compose up

# Or run in background
docker-compose up -d
```

#### Manual Docker Build

```bash
# Build the image
docker build -t chatvote:latest .

# Run with .env file
docker run --env-file .env -p 8080:8080 chatvote:latest

# Run with mounted ADC credentials
ADC=~/.config/gcloud/application_default_credentials.json && \
docker run --env-file .env \
  -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/keys/adc.json \
  -e GOOGLE_CLOUD_PROJECT=chatvote-dev \
  -v ${ADC}:/tmp/keys/adc.json:ro \
  -p 8080:8080 \
  chatvote:latest
```

---

## Testing

### End-to-End Tests

Requires a running backend instance:

```bash
# Run all WebSocket tests
poetry run pytest tests/test_websocket_app.py -s

# Run a specific test
poetry run pytest tests/test_websocket_app.py -k test_get_chat_answer -s
```

### Linting & Type Checking

```bash
# Run ruff linter
poetry run ruff check .

# Run ruff formatter
poetry run ruff format .

# Run mypy type checker
poetry run mypy src/
```

---

## Firebase Management

> Run these commands from the `firebase/` directory.

### Prerequisites

```bash
npm install -g firebase-tools
firebase login
npm install -g node-firestore-import-export
```

### Select Environment

```bash
firebase use dev   # or 'prod'
```

### Deploy Firebase Resources

```bash
# Firestore rules
firebase deploy --only firestore:rules

# Storage rules
firebase deploy --only storage

# Firestore indexes
firebase deploy --only firestore:indexes

# All functions
firebase deploy --only functions

# Specific function
firebase deploy --only functions:on_party_document_upload
```

### Data Management

#### Export Party Data

```bash
firestore-export \
  --accountCredentials ../chatvote-dev-firebase-adminsdk.json \
  --backupFile firestore_data/dev/parties.json \
  --nodePath parties -p
```

#### Import Party Data

```bash
firestore-import \
  --accountCredentials ../chatvote-dev-firebase-adminsdk.json \
  --backupFile firestore_data/dev/parties.json \
  --nodePath parties
```

#### Migrate Dev to Prod

1. Export from dev
2. Replace storage URLs: `chatvote-dev.firebasestorage.app` → `chatvote.firebasestorage.app`
3. Import to prod

---

## Project Structure

```
CHATVOTE-BackEnd/
├── src/
│   ├── aiohttp_app.py          # Main HTTP application & routes
│   ├── websocket_app.py        # Socket.IO event handlers
│   ├── chatbot_async.py        # LLM response generation
│   ├── llms.py                 # LLM configuration & failover
│   ├── vector_store_helper.py  # Qdrant operations
│   ├── firebase_service.py     # Firestore operations
│   ├── prompts.py              # French prompt templates
│   ├── prompts_en.py           # English prompt templates
│   ├── utils.py                # Utility functions
│   ├── i18n/                   # Internationalization
│   │   ├── locales/
│   │   │   ├── en.json
│   │   │   └── fr.json
│   │   └── translator.py
│   ├── models/                 # Pydantic models
│   │   ├── candidate.py
│   │   ├── party.py
│   │   ├── chat.py
│   │   ├── dtos.py
│   │   └── vote.py
│   └── services/               # Background services
│       ├── candidate_indexer.py
│       ├── candidate_website_scraper.py
│       ├── firestore_listener.py
│       ├── manifesto_indexer.py
│       ├── municipalities_sync.py
│       └── scheduler.py
├── firebase/
│   ├── functions/              # Firebase Functions (PDF ingestion)
│   │   └── main.py
│   ├── firestore_data/         # Data exports
│   ├── firestore.rules
│   └── storage.rules
├── tests/
│   └── test_websocket_app.py
├── data/
│   └── scripts/                # Data management notebooks
├── docs/
│   └── technical-stack.md      # Detailed technical documentation
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## API Reference

### REST Endpoints

| Method | Endpoint                             | Description                            |
| ------ | ------------------------------------ | -------------------------------------- |
| GET    | `/healthz`                           | Health check (Kubernetes-compatible)   |
| GET    | `/api/v1/assistant`                  | Get ChatVote assistant metadata        |
| POST   | `/api/v1/get-parliamentary-question` | Fetch relevant parliamentary questions |

### Admin Endpoints

| Method | Endpoint                                               | Description                        |
| ------ | ------------------------------------------------------ | ---------------------------------- |
| POST   | `/api/v1/admin/index-all-manifestos`                   | Re-index all party manifestos      |
| POST   | `/api/v1/admin/index-party-manifesto/{party_id}`       | Index specific party               |
| POST   | `/api/v1/admin/index-all-candidates`                   | Re-index all candidate websites    |
| POST   | `/api/v1/admin/index-candidate-website/{candidate_id}` | Index specific candidate           |
| GET    | `/api/v1/admin/listener-status`                        | Check Firestore listener status    |
| POST   | `/api/v1/admin/reset-rate-limit`                       | Reset LLM rate limit flags         |
| GET    | `/api/v1/admin/debug-qdrant`                           | Debug Qdrant party collection      |
| GET    | `/api/v1/admin/debug-candidates-qdrant`                | Debug Qdrant candidates collection |
| POST   | `/api/v1/admin/test-rag-search`                        | Test RAG search                    |

### WebSocket Events

#### Client → Server

| Event                                   | Description                      |
| --------------------------------------- | -------------------------------- |
| `chat_session_init`                     | Initialize a chat session        |
| `chat_answer_request`                   | Request a chat response          |
| `chat_summary_request`                  | Request conversation summary     |
| `pro_con_perspective_request`           | Request fact-check for party     |
| `candidate_pro_con_perspective_request` | Request fact-check for candidate |
| `voting_behavior_request`               | Request voting history analysis  |

#### Server → Client

| Event                           | Description                |
| ------------------------------- | -------------------------- |
| `chat_session_initialized`      | Session ready              |
| `responding_parties_selected`   | Which parties will respond |
| `sources_ready`                 | RAG sources identified     |
| `party_response_chunk_ready`    | Streaming response chunk   |
| `stream_reset`                  | LLM fallback occurred      |
| `party_response_complete`       | Full response complete     |
| `quick_replies_and_title_ready` | Suggested follow-ups       |
| `chat_response_complete`        | All responses complete     |
| `voting_behavior_result`        | Individual vote record     |
| `voting_behavior_summary_chunk` | Streaming vote summary     |
| `voting_behavior_complete`      | Vote analysis complete     |

---

## Qdrant Collections

| Collection                        | Content                      | Namespace                            |
| --------------------------------- | ---------------------------- | ------------------------------------ |
| `all_parties_{env}`               | Party manifestos (PDFs)      | `{party_id}`                         |
| `candidates_websites_{env}`       | Scraped candidate websites   | `{candidate_id}`                     |
| `justified_voting_behavior_{env}` | Parliamentary voting records | `vote_summary`                       |
| `parliamentary_questions_{env}`   | Parliamentary questions      | `{party_id}-parliamentary-questions` |

---

## License

This project is **source-available** under the **PolyForm Noncommercial 1.0.0** license.

- Free for **non-commercial** use (see LICENSE for permitted uses)
- Share the license text and `Required Notice:` lines when distributing
- Based on the open-source [wahl.chat](https://github.com/wahlchat) project - French adaptation

---

## Contributing

> Need help? Contact us at info@chatvote.org

### Development Workflow

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run linting and tests
5. Submit a pull request

### Code Style

- Python code follows [Ruff](https://docs.astral.sh/ruff/) formatting
- Type hints are enforced via [mypy](https://mypy.readthedocs.io/)
- Pre-commit hooks ensure consistent formatting

---

## Acknowledgments

- [wahl.chat](https://github.com/wahlchat) - Original German federal election chatbot
- [LangChain](https://langchain.com/) - LLM orchestration framework
- [Qdrant](https://qdrant.tech/) - Vector database
- [Firebase](https://firebase.google.com/) - Backend infrastructure
