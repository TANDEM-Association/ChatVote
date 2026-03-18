# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

import enum
from pydantic import BaseModel, Field, field_validator
from typing import List, Literal, Optional

from src.models.general import LLMSize
from src.models.vote import Vote
from .chat import Message
from .party import Party


class CreateSessionRequest(BaseModel):
    party_id: str = Field(
        ..., description="The ID of the party the user is chatting with"
    )
    user_id: str = Field(..., description="The ID of the user")


class ChatAnswerRequest(BaseModel):
    user_id: str = Field(..., description="The ID of the user")
    chat_session_id: str = Field(..., description="The ID of the chat session")
    user_message: str = Field(..., description="The user message to answer")


class GroupChatDto(BaseModel):
    chat_history: List[Message] = Field(..., description="The chat history")
    pre_selected_parties: List[Party] = Field(
        ..., description="The pre selected parties"
    )


class GroupChatResponseDto(BaseModel):
    new_messages: List[Message] = Field(..., description="The chat history")
    current_chat_title: str = Field(..., description="The current chat title")
    quick_replies: List[str] = Field(..., description="The quick replies")


class StatusIndicator(str, enum.Enum):
    ERROR = "error"
    SUCCESS = "success"


class ChatScope(str, enum.Enum):
    """Defines the geographic scope of the chat session."""

    NATIONAL = "national"  # Search in all manifestos + all candidate websites
    LOCAL = (
        "local"  # Search in manifestos + candidate websites filtered by municipality
    )


class Status(BaseModel):
    indicator: StatusIndicator = Field(..., description="The status of the event")
    message: str = Field(..., description="The message")


class InitChatSessionDto(BaseModel):
    session_id: str = Field(..., description="The ID of the chat session")
    chat_history: List[Message] = Field(..., description="The chat history")
    current_title: str = Field(..., description="The current chat title")
    chat_response_llm_size: LLMSize = Field(
        description="The size of the LLM model to use for chat response generation",
        default=LLMSize.LARGE,
    )
    last_quick_replies: List[str] = Field(
        description="The last quick replies that were shown to the user", default=[]
    )
    is_cacheable: bool = Field(
        description="Whether the chat history is cacheable or not", default=True
    )
    scope: ChatScope = Field(
        description="The geographic scope of the chat session (national or local)",
        default=ChatScope.NATIONAL,
    )
    municipality_code: Optional[str] = Field(
        description="The INSEE code of the municipality. Required when scope is LOCAL.",
        default=None,
    )
    electoral_list_panel_numbers: List[int] = Field(
        description="Panel numbers of electoral lists selected by the user for local scope.",
        default=[],
    )
    selected_electoral_lists: List[dict] = Field(
        description="Details of electoral lists selected by the user (panel_number, list_label, list_short_label, head_first_name, head_last_name).",
        default=[],
    )
    locale: Literal["fr", "en"] = Field(
        description="The locale for responses (fr or en). Defaults to French.",
        default="fr",
    )


class ChatSessionInitializedDto(BaseModel):
    session_id: Optional[str] = Field(
        ..., description="The ID of the chat session if applicable"
    )
    status: Status = Field(..., description="The status of the event")


class ProConPerspectiveRequestDto(BaseModel):
    request_id: str = Field(..., description="The ID of the Pro/Con assessment request")
    party_id: str = Field(
        ..., description="The ID of the party the user is chatting with"
    )
    last_user_message: str = Field(..., description="The last user message")
    last_assistant_message: str = Field(..., description="The last assistant message")


class ProConPerspectiveDto(BaseModel):
    request_id: Optional[str] = Field(
        ..., description="The ID of the Pro/Con assessment request if applicable"
    )
    message: Optional[Message] = Field(
        default=None, description="The Pro/Con assessment message"
    )
    status: Status = Field(..., description="The status of the event")


class CandidateProConPerspectiveRequestDto(BaseModel):
    """Request DTO for generating a Pro/Con perspective for a candidate's response."""

    request_id: str = Field(..., description="The ID of the Pro/Con assessment request")
    candidate_id: str = Field(
        ..., description="The ID of the candidate the user is chatting with"
    )
    last_user_message: str = Field(..., description="The last user message")
    last_assistant_message: str = Field(..., description="The last assistant message")


class CandidateProConPerspectiveDto(BaseModel):
    """Response DTO for a candidate's Pro/Con perspective assessment."""

    request_id: Optional[str] = Field(
        ..., description="The ID of the Pro/Con assessment request if applicable"
    )
    candidate_id: Optional[str] = Field(
        default=None, description="The ID of the candidate"
    )
    message: Optional[Message] = Field(
        default=None, description="The Pro/Con assessment message"
    )
    status: Status = Field(..., description="The status of the event")


class VotingBehaviorRequestDto(BaseModel):
    request_id: str = Field(..., description="The ID of the voting behavior request")
    party_id: str = Field(
        ..., description="The ID of the party the user is chatting with"
    )
    last_user_message: str = Field(..., description="The last user message")
    last_assistant_message: str = Field(..., description="The last assistant message")
    summary_llm_size: LLMSize = Field(
        description="The LLM size to use for voting behavior summary generation",
        default=LLMSize.LARGE,
    )
    user_is_logged_in: bool = Field(
        description="Whether the user is logged in or not", default=False
    )


class ParliamentaryQuestionRequestDto(BaseModel):
    request_id: str = Field(
        ..., description="The ID of the parliamentary question request"
    )
    party_id: str = Field(
        ..., description="The ID of the party the user is chatting with"
    )
    last_user_message: str = Field(..., description="The last user message")
    last_assistant_message: str = Field(..., description="The last assistant message")


class VotingBehaviorVoteDto(BaseModel):
    request_id: str = Field(..., description="The ID of the voting behavior request")
    vote: Vote = Field(..., description="The vote")


class VotingBehaviorSummaryChunkDto(BaseModel):
    request_id: str = Field(..., description="The ID of the voting behavior request")
    chunk_index: int = Field(..., description="The index of the chunk in the summary")
    summary_chunk: str = Field(..., description="The message content")
    is_end: bool = Field(
        ..., description="Whether this is the last chunk of the summary"
    )


class VotingBehaviorDto(BaseModel):
    request_id: Optional[str] = Field(
        ..., description="The ID of the voting behavior request if applicable"
    )
    message: str = Field(..., description="The voting behavior message")
    status: Status = Field(..., description="The status of the event")
    votes: list[Vote] = Field(..., description="The votes")
    rag_query: Optional[str] = Field(
        ..., description="The RAG query that was used to get the votes"
    )


class ParliamentaryQuestionDto(BaseModel):
    request_id: Optional[str] = Field(
        ..., description="The ID of the parliamentary question request if applicable"
    )
    status: Status = Field(..., description="The status of the event")
    parliamentary_questions: list[Vote] = Field(
        ..., description="The parliamentary questions"
    )
    rag_query: Optional[str] = Field(
        ..., description="The RAG query that was used to get the votes"
    )


class ChatUserMessageDto(BaseModel):
    session_id: str = Field(
        ..., description="The ID of the chat session to which the message belongs"
    )
    user_message: str = Field(
        ..., description="The user message to answer", max_length=500
    )
    party_ids: List[str] = Field(
        ..., description="The IDs of the parties that are part of the chat session"
    )
    user_is_logged_in: bool = Field(
        description="Whether the user is logged in or not", default=False
    )
    scope: ChatScope = Field(
        description="The geographic scope of the chat (national or local)",
        default=ChatScope.NATIONAL,
    )
    municipality_code: Optional[str] = Field(
        description="The INSEE code of the municipality. Required when scope is LOCAL.",
        default=None,
    )
    locale: Literal["fr", "en"] = Field(
        description="The locale for responses (fr or en). Defaults to French.",
        default="fr",
    )
    candidate_ids: List[str] = Field(
        description="Optional list of specific candidate IDs to target in retrieval.",
        default_factory=list,
    )

    @field_validator("session_id")
    def session_id_must_not_be_empty(cls, value):
        if not value.strip():  # Check for empty or whitespace-only strings
            raise ValueError("Session ID cannot be empty or whitespace.")
        return value


class TitleDto(BaseModel):
    session_id: str = Field(..., description="The ID of the chat session to update")
    title: str = Field(..., description="The new title of the chat session")


class SourcesDto(BaseModel):
    session_id: str = Field(
        ..., description="The ID of the chat session which the sources belong to"
    )
    sources: List[dict] = Field(
        ..., description="The sources for the response that will be generated"
    )
    party_id: str = Field(
        ...,
        description="The ID of the party for which the sources were retrieved.",
    )
    rag_query: Optional[List[str]] = Field(
        ..., description="The RAG query that was used to get the sources if any"
    )


class RespondingPartiesDto(BaseModel):
    session_id: str = Field(
        ..., description="The ID of the chat session to which the message belongs"
    )
    party_ids: List[str] = Field(
        ..., description="The IDs of the parties that are responding"
    )


class PartyResponseChunkDto(BaseModel):
    session_id: str = Field(
        ..., description="The ID of the chat session to which the message belongs"
    )
    party_id: Optional[str] = Field(
        ...,
        description="The ID of the party the message is coming from. None for general Perplexity chat",
    )
    chunk_index: int = Field(..., description="The index of the chunk in the response")
    chunk_content: str = Field(..., description="The message content")
    is_end: bool = Field(
        ..., description="Whether this is the last chunk of the response"
    )


class StreamResetDto(BaseModel):
    """Emitted when the LLM stream has to restart due to a fallback (e.g., rate limit).

    When this event is received, the frontend should clear the current partial response
    and prepare to receive a new complete response from the fallback LLM.
    """

    session_id: str = Field(..., description="The ID of the chat session")
    party_id: Optional[str] = Field(..., description="The ID of the party/responder")
    reason: str = Field(
        ...,
        description="The reason for the reset (e.g., 'Rate limit on google-gemini-2.5-flash')",
    )


class PartyResponseCompleteDto(BaseModel):
    session_id: str = Field(
        ..., description="The ID of the chat session to which the message belongs"
    )
    party_id: Optional[str] = Field(
        ...,
        description="The ID of the party the message is coming from. None for general perplexity",
    )
    complete_message: str = Field(..., description="The complete message content")
    status: Status = Field(..., description="The status of the event")


class ChatResponseCompleteDto(BaseModel):
    session_id: Optional[str] = Field(
        ...,
        description="The ID of the chat session to which the message belongs if applicable",
    )
    status: Status = Field(..., description="The status of the event")


class QuickRepliesAndTitleDto(BaseModel):
    session_id: str = Field(
        ..., description="The ID of the chat session to which the message belongs"
    )
    quick_replies: List[str] = Field(..., description="The quick replies for the user")
    title: str = Field(..., description="The new title of the chat session")


class RequestSummaryDto(BaseModel):
    chat_history: List[Message] = Field(..., description="The chat history")


class SummaryDto(BaseModel):
    chat_summary: str = Field(..., description="The chat summary")
    status: Status = Field(..., description="The status of the event")
