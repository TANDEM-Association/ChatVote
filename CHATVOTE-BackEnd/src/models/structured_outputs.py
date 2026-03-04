# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

from pydantic import BaseModel, Field


class RAG(BaseModel):
    """RAG chain output."""

    chat_answer: str = Field(
        description="Your short answer to the user's question in Markdown format with formatting and paragraphs."
    )
    chat_title: str = Field(
        description="The short chat title in plain text. It should describe the chat concisely in 3-5 words."
    )


class QuickReplyGenerator(BaseModel):
    """Quick reply generator output."""

    quick_replies: list[str] = Field(
        description="List of three quick replies as strings."
    )


class PartyListGenerator(BaseModel):
    """Party list generator output."""

    party_id_list: list[str] = Field(
        description="List of party/list IDs from which the user wants to get a response. "
        "Use 'chat-vote' for general questions about elections or ChatVote itself."
    )


class QuestionTypeClassifier(BaseModel):
    """Question type classifier output."""

    non_party_specific_question: str = Field(
        description="The user's question, reformulated as if addressed directly to a party/list."
    )
    is_comparing_question: bool = Field(
        description="True if it's an explicit comparison question, False otherwise."
    )


class ChatSummaryGenerator(BaseModel):
    """Chat summary generator output."""

    chat_summary: str = Field(
        description="The main guiding questions that the parties/lists have answered."
    )


class GroupChatTitleQuickReplyGenerator(BaseModel):
    """Title and quick reply generator output."""

    chat_title: str = Field(
        description="A short title that describes the chat concisely in 3-5 words."
    )
    quick_replies: list[str] = Field(
        description="List of three quick replies as strings."
    )


class RerankingOutput(BaseModel):
    """Reranking model output."""

    reranked_doc_indices: list[int] = Field(
        description="List of document indices sorted by decreasing usefulness."
    )


class EntityDetector(BaseModel):
    """Detection of parties and candidates mentioned in user message."""

    party_ids: list[str] = Field(
        description="List of party IDs mentioned by the user (e.g., 'lr', 'ps', 'europe-ecologie-les-verts'). "
        "Empty list if no party is mentioned."
    )
    candidate_ids: list[str] = Field(
        description="List of candidate IDs mentioned by the user (e.g., 'cand-paris-001'). "
        "Empty list if no candidate is mentioned."
    )
    needs_clarification: bool = Field(
        description="True if the question is too general and requires the user to specify a party or candidate. "
        "False if at least one party or candidate is mentioned or can be inferred."
    )
    clarification_message: str = Field(
        description="Message to display if needs_clarification is True, asking the user to specify a party or candidate. "
        "Empty string if needs_clarification is False."
    )
    reformulated_question: str = Field(
        description="The user's question reformulated in a general way, as if addressed to a party/candidate."
    )
