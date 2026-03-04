"""Export Pydantic model JSON Schemas for TypeScript type generation.

Outputs a JSON object to stdout with:
  - schemas: dict of model_name -> JSON Schema
  - socket_events: server_to_client and client_to_server event maps
  - name_map: python_name -> typescript_name remaps

Usage:
  poetry run python scripts/generate_ts_types.py
"""

import json
import sys
from pathlib import Path

# Add project root to path so src.models imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.chat import Message, Role
from src.models.party import Party
from src.models.candidate import Candidate
from src.models.vote import Vote, VotingResults, VotingResultsOverall, VotingResultsByParty, Link
from src.models.general import LLMSize
from src.models.assistant import Assistant
from src.models.dtos import (
    ChatScope,
    StatusIndicator,
    Status,
    InitChatSessionDto,
    ChatSessionInitializedDto,
    ChatUserMessageDto,
    SourcesDto,
    RespondingPartiesDto,
    PartyResponseChunkDto,
    StreamResetDto,
    PartyResponseCompleteDto,
    QuickRepliesAndTitleDto,
    ChatResponseCompleteDto,
    ProConPerspectiveRequestDto,
    ProConPerspectiveDto,
    CandidateProConPerspectiveRequestDto,
    CandidateProConPerspectiveDto,
    VotingBehaviorRequestDto,
    VotingBehaviorVoteDto,
    VotingBehaviorSummaryChunkDto,
    VotingBehaviorDto,
    ParliamentaryQuestionRequestDto,
    ParliamentaryQuestionDto,
    TitleDto,
    SummaryDto,
)

# Models to export with optional TS name remaps.
# If ts_name is None, the Python class name is used as-is.
MODELS: list[tuple[type, str | None]] = [
    # Domain models
    (Party, None),
    (Candidate, None),
    (Vote, None),
    (VotingResults, None),
    (VotingResultsOverall, None),
    (VotingResultsByParty, None),
    (Link, None),
    (Message, None),
    (Assistant, None),
    # Response/request DTOs
    (Status, None),
    (InitChatSessionDto, None),
    (ChatSessionInitializedDto, None),
    (ChatUserMessageDto, None),
    (SourcesDto, None),
    (RespondingPartiesDto, None),
    (PartyResponseChunkDto, None),
    (StreamResetDto, None),
    (PartyResponseCompleteDto, None),
    (QuickRepliesAndTitleDto, None),
    (ChatResponseCompleteDto, None),
    (ProConPerspectiveRequestDto, None),
    (ProConPerspectiveDto, None),
    (CandidateProConPerspectiveRequestDto, None),
    (CandidateProConPerspectiveDto, None),
    (VotingBehaviorRequestDto, None),
    (VotingBehaviorVoteDto, None),
    (VotingBehaviorSummaryChunkDto, None),
    (VotingBehaviorDto, None),
    (ParliamentaryQuestionRequestDto, None),
    (ParliamentaryQuestionDto, None),
    (TitleDto, None),
    (SummaryDto, None),
]

# Enums are exported as their JSON Schema representation.
# Pydantic v2 str Enums produce {"enum": [...], "type": "string"}.
ENUMS: list[tuple[type, str | None]] = [
    (Role, None),
    (LLMSize, None),
    (ChatScope, None),
    (StatusIndicator, None),
]

# Socket.IO event map: event_name -> DTO class name (must match a key in MODELS).
SOCKET_EVENTS = {
    "server_to_client": {
        "chat_session_initialized": "ChatSessionInitializedDto",
        "sources_ready": "SourcesDto",
        "party_response_chunk_ready": "PartyResponseChunkDto",
        "party_response_complete": "PartyResponseCompleteDto",
        "quick_replies_and_title_ready": "QuickRepliesAndTitleDto",
        "chat_response_complete": "ChatResponseCompleteDto",
        "pro_con_perspective_complete": "ProConPerspectiveDto",
        "candidate_pro_con_perspective_complete": "CandidateProConPerspectiveDto",
        "responding_parties_selected": "RespondingPartiesDto",
        "voting_behavior_result": "VotingBehaviorVoteDto",
        "voting_behavior_summary_chunk": "VotingBehaviorSummaryChunkDto",
        "voting_behavior_complete": "VotingBehaviorDto",
        "stream_reset": "StreamResetDto",
    },
    "client_to_server": {
        "chat_session_init": "InitChatSessionDto",
        "chat_answer_request": "ChatUserMessageDto",
        "pro_con_perspective_request": "ProConPerspectiveRequestDto",
        "candidate_pro_con_perspective_request": "CandidateProConPerspectiveRequestDto",
        "voting_behavior_request": "VotingBehaviorRequestDto",
    },
}


def _get_enum_schema(enum_cls: type) -> dict:
    """Build a JSON Schema for a str Enum."""
    members = [m.value for m in enum_cls]  # type: ignore[attr-defined]
    return {"enum": members, "title": enum_cls.__name__, "type": "string"}


def _make_all_fields_required(schema: dict) -> dict:
    """Make all fields required in a JSON Schema.

    Pydantic v2 excludes fields with defaults from the ``required`` array,
    but ``model_dump()`` always includes them. TypeScript types should
    therefore treat every field as required (present in the JSON).
    Nullable fields keep their ``| null`` via ``anyOf``.
    """
    if "properties" in schema:
        schema["required"] = list(schema["properties"].keys())
    # Also fix nested $defs
    for defn in schema.get("$defs", {}).values():
        if "properties" in defn:
            defn["required"] = list(defn["properties"].keys())
    return schema


def main() -> None:
    schemas: dict[str, dict] = {}
    name_map: dict[str, str] = {}

    # Export Pydantic models
    for model_cls, ts_name in MODELS:
        py_name = model_cls.__name__
        schema = model_cls.model_json_schema()  # type: ignore[attr-defined]
        schema = _make_all_fields_required(schema)
        schemas[py_name] = schema
        if ts_name:
            name_map[py_name] = ts_name

    # Export enums
    for enum_cls, ts_name in ENUMS:
        py_name = enum_cls.__name__
        schema = _get_enum_schema(enum_cls)
        schemas[py_name] = schema
        if ts_name:
            name_map[py_name] = ts_name

    output = {
        "schemas": schemas,
        "socket_events": SOCKET_EVENTS,
        "name_map": name_map,
    }
    json.dump(output, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
