<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-04 -->

# src/models

## Purpose
Pydantic v2 data models shared across the entire backend. Defines domain entities (parties, candidates, votes, chat sessions), Socket.IO data transfer objects (DTOs), LLM metadata, and structured LLM output schemas used for function-calling / structured output calls. All models are imported by the service layer, websocket handlers, REST routes, and tests.

## Key Files
| File | Description |
|------|-------------|
| `party.py` | `Party` — political party/list entity with manifesto URL, logo, candidate, colours |
| `candidate.py` | `Candidate` — election candidate with municipality, party affiliations, presence score, website; properties `full_name`, `is_in_coalition`, `is_national_candidate` |
| `vote.py` | `Vote`, `VotingResults`, `VotingResultsByParty`, `VotingResultsOverall`, `Link` — parliamentary voting record structure |
| `chat.py` | `Message`, `Role`, `ChatSession`, `GroupChatSession`, `CachedResponse`, `ProConAssessment` — chat session and message types; `GroupChatSession` carries LLM size preference, scope, municipality code, and locale |
| `dtos.py` | All Socket.IO event payloads (init, chunks, complete, pro/con, voting behaviour, parliamentary questions, stream reset, quick replies) and REST request/response DTOs |
| `general.py` | `LLMSize` enum (`small` | `large`); `LLM` model — provider instance, priority, capacity, rate-limit flag, premium/backup flags |
| `assistant.py` | `Assistant` model; `CHATVOTE_ASSISTANT` singleton; `ASSISTANT_ID = "chat-vote"` constant |
| `structured_outputs.py` | Pydantic schemas for structured LLM outputs: `RAG`, `QuickReplyGenerator`, `PartyListGenerator`, `QuestionTypeClassifier`, `RerankingOutput`, `EntityDetector`, `GroupChatTitleQuickReplyGenerator` |

## For AI Agents

### Working In This Directory
- All models use Pydantic v2; use `model_dump()` and `model_validate()`, not `.dict()` or `.parse_obj()`
- `dtos.py` defines the Socket.IO wire format — any change here must be coordinated with `src/websocket_app.py` and the frontend's `socket.types.ts`
- `structured_outputs.py` schemas are passed to `llm.with_structured_output(schema)` — field descriptions are part of the prompt to the model; keep them accurate
- `LLM` in `general.py` wraps a LangChain `BaseChatModel`; `is_at_rate_limit` is mutated at runtime by `src/llms.py`
- `ASSISTANT_ID = "chat-vote"` is used as a sentinel in `vector_store_helper.py` to decide whether to search all namespaces or a specific party namespace

### Testing Requirements
Models are tested implicitly through integration tests. For isolated unit tests:
```bash
poetry run pytest -k "model" -s
```
Pydantic validation errors surface at import or instantiation time; run `poetry run mypy src/models/` to catch type issues early.

### Common Patterns
- `ChatScope` enum (`national` | `local`) gates whether candidate searches are municipality-filtered
- `StreamResetDto` is emitted to clients when `StreamResetMarker` is received mid-stream, signalling the frontend to clear partial response
- `CachedResponse` stores `depth` and `user_message_depth` to allow cache hits at varying conversation lengths
- `GroupChatSession` is the in-memory session object maintained by `websocket_app.py`; it is not persisted to Firestore directly

## Dependencies

### Internal
- `src/models/general.py` is imported by `src/models/chat.py`, `src/models/dtos.py`, and `src/llms.py`
- `src/models/assistant.py` is imported by `src/utils.py` and `src/vector_store_helper.py`

### External
| Package | Purpose |
|---------|---------|
| `pydantic` ~2.10 | Model definition, validation, serialisation |
| `langchain-core` | `BaseChatModel` base class used in `general.py` |

<!-- MANUAL: -->
