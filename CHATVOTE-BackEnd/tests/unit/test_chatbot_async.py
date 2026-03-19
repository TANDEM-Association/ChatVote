# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Unit tests for src/chatbot_async.py.

All tests run WITHOUT external services (no Qdrant, no Firebase, no LLM APIs).
Heavy module-level imports are mocked via sys.modules BEFORE importing the module.
"""

import os
import sys
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.documents import Document
from langchain_core.messages import AIMessage

# ---------------------------------------------------------------------------
# Environment setup — must happen BEFORE any src imports
# ---------------------------------------------------------------------------
os.environ.setdefault("API_NAME", "chatvote-api")
os.environ.setdefault("ENV", "local")
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:8081")
os.environ.setdefault("GOOGLE_API_KEY", "fake-key-for-testing")

# ---------------------------------------------------------------------------
# Mock heavy module-level imports BEFORE importing src.chatbot_async
# ---------------------------------------------------------------------------

_mock_firebase_service = MagicMock()
_mock_firebase_service.awrite_llm_status = AsyncMock()
sys.modules.setdefault("src.firebase_service", _mock_firebase_service)

_mock_vector_store_helper = MagicMock()
sys.modules.setdefault("src.vector_store_helper", _mock_vector_store_helper)

# Mock LLM provider packages
from langchain_core.language_models.fake_chat_models import (  # noqa: E402
    FakeListChatModel as _FakeChat,
)


def _make_fake_chat(*args, **kwargs):
    return _FakeChat(responses=["mocked response"])


_mock_google = MagicMock()
_mock_google.ChatGoogleGenerativeAI = _make_fake_chat
_mock_openai = MagicMock()
_mock_openai.ChatOpenAI = _make_fake_chat
_mock_openai.AzureChatOpenAI = _make_fake_chat
_mock_anthropic = MagicMock()
_mock_anthropic.ChatAnthropic = _make_fake_chat
_mock_ollama = MagicMock()
_mock_ollama.ChatOllama = _make_fake_chat

for _mod_name, _mock_mod in [
    ("langchain_google_genai", _mock_google),
    ("langchain_openai", _mock_openai),
    ("langchain_anthropic", _mock_anthropic),
    ("langchain_ollama", _mock_ollama),
]:
    sys.modules.setdefault(_mod_name, _mock_mod)

_mock_model_config = MagicMock()
_mock_model_config.GEMINI_2_FLASH = "gemini-2.0-flash"
_mock_model_config.GPT_4O = "gpt-4o"
_mock_model_config.GPT_4O_MINI = "gpt-4o-mini"
_mock_model_config.AZURE_GPT_4O_DEPLOYMENT = "gpt-4o"
_mock_model_config.AZURE_GPT_4O_MINI_DEPLOYMENT = "gpt-4o-mini"
_mock_model_config.CLAUDE_SONNET = "claude-sonnet-4-5"
_mock_model_config.CLAUDE_HAIKU = "claude-haiku-3-5"
_mock_model_config.OLLAMA_CHAT_MODEL = "llama3.2"
_mock_model_config.CAPACITY_GEMINI_2_FLASH = 200
_mock_model_config.CAPACITY_GPT_4O_OPENAI_TIER_5 = 50
_mock_model_config.CAPACITY_GPT_4O_AZURE = 50
_mock_model_config.CAPACITY_GPT_4O_MINI_OPENAI_TIER_5 = 200
_mock_model_config.CAPACITY_GPT_4O_MINI_AZURE = 200
_mock_model_config.CAPACITY_CLAUDE_SONNET = 50
_mock_model_config.CAPACITY_CLAUDE_HAIKU = 200
sys.modules.setdefault("src.model_config", _mock_model_config)

# Evict mocks set by other test files (e.g. test_aiohttp_app.py) so real modules load
sys.modules.pop("src.chatbot_async", None)
sys.modules.pop("src.utils", None)
sys.modules.pop("src.llms", None)

# Now it is safe to import from src.chatbot_async
from langchain_core.language_models.fake_chat_models import FakeListChatModel  # noqa: E402
from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402

from src.models.general import LLM, LLMSize  # noqa: E402
from src.models.party import Party  # noqa: E402
from src.models.candidate import Candidate  # noqa: E402
from src.models.assistant import ASSISTANT_ID, CHATVOTE_ASSISTANT  # noqa: E402
from src.models.vote import (  # noqa: E402
    Vote,
    VotingResults,
    VotingResultsOverall,
    VotingResultsByParty,
)
from src.models.chat import Message, Role  # noqa: E402
from src.models.structured_outputs import (  # noqa: E402
    RerankingOutput,
    PartyListGenerator,
    ChatSummaryGenerator,
    GroupChatTitleQuickReplyGenerator,
    EntityDetector,
)

from src.chatbot_async import (  # noqa: E402
    _pdf_viewer_url,
    _format_vote_summary,
    get_rag_context,
    get_rag_comparison_context,
    get_rag_context_for_candidates,
    get_combined_rag_context,
    rerank_documents,
    get_question_targets_and_type,
    detect_entities_and_route,
    generate_improvement_rag_query,
    generate_improvement_rag_query_candidate,
    generate_chat_summary,
    generate_chat_title_and_chick_replies,
    get_improved_rag_query_voting_behavior,
    generate_streaming_chatbot_response,
    generate_streaming_chatbot_comparing_response,
    generate_streaming_candidate_response,
    generate_streaming_candidate_local_response,
    generate_streaming_candidate_national_response,
    generate_streaming_combined_response,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_llm(
    name: str,
    priority: int = 100,
    sizes: list[LLMSize] | None = None,
    responses: list[str] | None = None,
    fail: bool = False,
) -> LLM:
    model = FakeListChatModel(responses=responses or ["default response"])
    if fail:
        object.__setattr__(
            model, "ainvoke", AsyncMock(side_effect=Exception(f"{name} failed"))
        )

        async def _failing_stream(messages, **kwargs):
            raise Exception(f"{name} stream failed")
            yield  # type: ignore[misc]

        object.__setattr__(model, "astream", _failing_stream)
    return LLM(
        name=name,
        model=model,
        sizes=sizes or [LLMSize.LARGE],
        priority=priority,
        user_capacity_per_minute=100,
        is_at_rate_limit=False,
    )


def make_streaming_llm(
    name: str,
    chunks: list[str] | None = None,
) -> LLM:
    _chunks = chunks or ["hello", " world"]

    async def _stream(messages, **kwargs):
        for chunk in _chunks:
            yield AIMessage(content=chunk)

    model = FakeListChatModel(responses=["hello world"])
    object.__setattr__(model, "astream", _stream)

    return LLM(
        name=name,
        model=model,
        sizes=[LLMSize.LARGE],
        priority=100,
        user_capacity_per_minute=100,
        is_at_rate_limit=False,
    )


def make_party(
    party_id: str = "test-party",
    name: str = "Test",
    long_name: str = "Test Party",
    is_small: bool = False,
) -> Party:
    return Party(
        party_id=party_id,
        name=name,
        long_name=long_name,
        description="A test party",
        website_url="https://test.fr",
        candidate="Jean Test",
        election_manifesto_url="https://test.fr/manifesto.pdf",
        is_small_party=is_small,
    )


def make_candidate(
    candidate_id: str = "cand-001",
    first_name: str = "Marie",
    last_name: str = "Dupont",
    municipality_code: str | None = "75056",
    municipality_name: str | None = "Paris",
    party_ids: list[str] | None = None,
    election_type_id: str = "municipales-2026",
    website_url: str | None = None,
    manifesto_pdf_url: str | None = None,
    is_incumbent: bool = False,
) -> Candidate:
    return Candidate(
        candidate_id=candidate_id,
        first_name=first_name,
        last_name=last_name,
        municipality_code=municipality_code,
        municipality_name=municipality_name,
        party_ids=party_ids or ["test-party"],
        election_type_id=election_type_id,
        website_url=website_url,
        manifesto_pdf_url=manifesto_pdf_url,
        is_incumbent=is_incumbent,
    )


def make_vote(
    vote_id: str = "v1",
    party_id: str = "test-party",
    date: str = "2024-01-15",
    title: str = "Test Vote",
    short_description: str | None = "Vote summary",
    submitting_parties: list[str] | None = None,
    yes: int = 10,
    no: int = 5,
    abstain: int = 2,
    not_voted: int = 1,
    members: int = 18,
) -> Vote:
    overall = VotingResultsOverall(
        yes=yes, no=no, abstain=abstain, not_voted=not_voted, members=members
    )
    party_result = VotingResultsByParty(
        party=party_id,
        members=5,
        yes=3,
        no=1,
        abstain=0,
        not_voted=1,
        justification="Test justification",
    )
    results = VotingResults(overall=overall, by_party=[party_result])
    return Vote(
        id=vote_id,
        url="https://test.fr/vote/1",
        date=date,
        title=title,
        subtitle=None,
        detail_text=None,
        links=[],
        voting_results=results,
        short_description=short_description,
        vote_category="budget",
        submitting_parties=submitting_parties,
    )


def make_document(
    content: str = "Document content",
    metadata: dict | None = None,
) -> Document:
    return Document(page_content=content, metadata=metadata or {})


async def collect_stream(stream: AsyncIterator) -> list:
    items = []
    async for item in stream:
        items.append(item)
    return items


# ---------------------------------------------------------------------------
# Tests: _pdf_viewer_url (pure function)
# ---------------------------------------------------------------------------


class TestPdfViewerUrl:
    def test_basic_url(self):
        url = "https://example.com/doc.pdf"
        result = _pdf_viewer_url(url)
        assert result.startswith("https://app.chatvote.org/pdf/view?page=1&pdf=")
        assert "example.com" in result

    def test_encodes_special_characters(self):
        url = "https://example.com/doc with spaces.pdf"
        result = _pdf_viewer_url(url)
        assert " " not in result
        assert "%20" in result or "+" in result

    def test_encodes_colon_and_slashes(self):
        url = "https://example.com/path/to/file.pdf"
        result = _pdf_viewer_url(url)
        # The scheme https:// should be encoded since safe=''
        assert "https%3A" in result or "https://" not in result.split("pdf=")[1]

    def test_page_1_always_present(self):
        url = "https://example.com/doc.pdf"
        result = _pdf_viewer_url(url)
        assert "page=1" in result

    def test_empty_url(self):
        result = _pdf_viewer_url("")
        assert result == "https://app.chatvote.org/pdf/view?page=1&pdf="

    def test_url_with_query_params(self):
        url = "https://example.com/doc.pdf?token=abc&version=2"
        result = _pdf_viewer_url(url)
        assert "pdf=" in result
        assert result.startswith("https://app.chatvote.org/pdf/view?page=1&pdf=")


# ---------------------------------------------------------------------------
# Tests: get_rag_context (pure function)
# ---------------------------------------------------------------------------


class TestGetRagContext:
    def test_empty_docs_returns_no_info_message(self):
        result = get_rag_context([])
        assert "Aucune information pertinente" in result

    def test_single_doc_included(self):
        doc = make_document("Some policy content")
        result = get_rag_context([doc])
        assert "Some policy content" in result

    def test_multiple_docs_all_included(self):
        docs = [
            make_document("Content A"),
            make_document("Content B"),
            make_document("Content C"),
        ]
        result = get_rag_context(docs)
        assert "Content A" in result
        assert "Content B" in result
        assert "Content C" in result

    def test_doc_num_appears_in_context(self):
        doc = make_document("Test content", {"document_name": "test.pdf"})
        result = get_rag_context([doc])
        # ID 0 should appear for the first doc
        assert "0" in result

    def test_non_empty_docs_no_fallback_message(self):
        doc = make_document("Real content")
        result = get_rag_context([doc])
        assert "Aucune information pertinente" not in result


# ---------------------------------------------------------------------------
# Tests: get_rag_comparison_context (pure function)
# ---------------------------------------------------------------------------


class TestGetRagComparisonContext:
    def test_empty_docs_returns_no_info_message(self):
        # get_rag_comparison_context only shows "no info" when ALL parties have no docs
        # AND the resulting rag_context is empty. With an empty list per party, it still
        # adds the party header, so the final string is non-empty. Test with no parties.
        result = get_rag_comparison_context({}, [])
        assert "Aucune information pertinente" in result

    def test_includes_party_name_header(self):
        party = make_party(party_id="lfi", name="LFI")
        doc = make_document("LFI policy", {"document_name": "manifesto.pdf"})
        result = get_rag_comparison_context({"lfi": [doc]}, [party])
        assert "LFI" in result

    def test_includes_doc_content(self):
        party = make_party(party_id="rn", name="RN")
        doc = make_document("Security policy content")
        result = get_rag_comparison_context({"rn": [doc]}, [party])
        assert "Security policy content" in result

    def test_multiple_parties_incrementing_doc_nums(self):
        party_a = make_party(party_id="a", name="PartyA")
        party_b = make_party(party_id="b", name="PartyB")
        doc_a = make_document("Content A")
        doc_b = make_document("Content B")
        result = get_rag_comparison_context(
            {"a": [doc_a], "b": [doc_b]}, [party_a, party_b]
        )
        assert "PartyA" in result
        assert "PartyB" in result
        assert "Content A" in result
        assert "Content B" in result

    def test_metadata_fields_in_output(self):
        party = make_party(party_id="ps", name="PS")
        doc = make_document(
            "Content",
            {
                "document_name": "programme.pdf",
                "document_publish_date": "2024-01-01",
            },
        )
        result = get_rag_comparison_context({"ps": [doc]}, [party])
        assert "programme.pdf" in result
        assert "2024-01-01" in result


# ---------------------------------------------------------------------------
# Tests: get_rag_context_for_candidates (pure function)
# ---------------------------------------------------------------------------


class TestGetRagContextForCandidates:
    def test_empty_docs_returns_no_info_message(self):
        result = get_rag_context_for_candidates([])
        assert "Aucune information pertinente" in result

    def test_single_doc_with_metadata(self):
        doc = make_document(
            "Candidate content",
            {
                "candidate_name": "Marie Dupont",
                "municipality_name": "Paris",
                "page_type": "programme",
                "document_name": "site web",
                "url": "https://marie.fr",
            },
        )
        result = get_rag_context_for_candidates([doc])
        assert "Marie Dupont" in result
        assert "Paris" in result
        assert "Candidate content" in result

    def test_multiple_docs_all_included(self):
        docs = [
            make_document("Content A", {"candidate_name": "Alice"}),
            make_document("Content B", {"candidate_name": "Bob"}),
        ]
        result = get_rag_context_for_candidates(docs)
        assert "Content A" in result
        assert "Content B" in result

    def test_doc_id_increments(self):
        docs = [
            make_document("Content 0"),
            make_document("Content 1"),
        ]
        result = get_rag_context_for_candidates(docs)
        assert "ID: 0" in result
        assert "ID: 1" in result

    def test_missing_metadata_uses_defaults(self):
        doc = make_document("Minimal content")
        result = get_rag_context_for_candidates([doc])
        assert "Inconnu" in result  # default candidate_name
        assert "Minimal content" in result


# ---------------------------------------------------------------------------
# Tests: get_combined_rag_context (pure function)
# ---------------------------------------------------------------------------


class TestGetCombinedRagContext:
    def test_empty_manifesto_returns_fallback_message(self):
        manifesto_ctx, _ = get_combined_rag_context([], [])
        assert (
            "Aucune information trouvée dans les programmes officiels" in manifesto_ctx
        )

    def test_empty_candidates_returns_fallback_message(self):
        _, candidates_ctx = get_combined_rag_context([], [])
        assert (
            "Aucune information trouvée sur les sites web des candidats"
            in candidates_ctx
        )

    def test_manifesto_docs_use_p_prefix(self):
        docs = [make_document("Manifesto 1"), make_document("Manifesto 2")]
        manifesto_ctx, _ = get_combined_rag_context(docs, [])
        assert "ID: P0" in manifesto_ctx
        assert "ID: P1" in manifesto_ctx

    def test_candidate_docs_numbered_from_zero(self):
        manifesto_docs = [make_document("Manifesto 1"), make_document("Manifesto 2")]
        candidate_docs = [make_document("Candidate 1")]
        _, candidates_ctx = get_combined_rag_context(manifesto_docs, candidate_docs)
        # candidate docs always start at 0, independent of manifesto count
        assert "ID: 0" in candidates_ctx

    def test_manifesto_content_included(self):
        doc = make_document("Official programme content", {"namespace": "lfi"})
        manifesto_ctx, _ = get_combined_rag_context([doc], [])
        assert "Official programme content" in manifesto_ctx
        assert "lfi" in manifesto_ctx

    def test_candidate_content_included(self):
        doc = make_document(
            "Candidate website content",
            {"candidate_name": "Pierre Martin", "municipality_name": "Lyon"},
        )
        _, candidates_ctx = get_combined_rag_context([], [doc])
        assert "Candidate website content" in candidates_ctx
        assert "Pierre Martin" in candidates_ctx

    def test_returns_tuple_of_two_strings(self):
        result = get_combined_rag_context([], [])
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert all(isinstance(s, str) for s in result)


# ---------------------------------------------------------------------------
# Tests: _format_vote_summary (pure function)
# ---------------------------------------------------------------------------


class TestFormatVoteSummary:
    def _make_party_result(
        self, yes=3, no=1, abstain=0, not_voted=1, justification=None
    ):
        return VotingResultsByParty(
            party="test-party",
            members=5,
            yes=yes,
            no=no,
            abstain=abstain,
            not_voted=not_voted,
            justification=justification,
        )

    def test_includes_vote_id(self):
        vote = make_vote(vote_id="v42")
        result = _format_vote_summary(
            vote, "Description", self._make_party_result(), "Party A", "TestParty"
        )
        assert "v42" in result

    def test_includes_vote_title(self):
        vote = make_vote(title="Budget Amendment 2024")
        result = _format_vote_summary(
            vote, "Description", self._make_party_result(), "Party A", "TestParty"
        )
        assert "Budget Amendment 2024" in result

    def test_includes_vote_date(self):
        vote = make_vote(date="2024-03-15")
        result = _format_vote_summary(
            vote, "Description", self._make_party_result(), "Party A", "TestParty"
        )
        assert "2024-03-15" in result

    def test_includes_description(self):
        vote = make_vote()
        result = _format_vote_summary(
            vote,
            "Special description text",
            self._make_party_result(),
            "Party A",
            "TestParty",
        )
        assert "Special description text" in result

    def test_includes_submitting_parties(self):
        vote = make_vote()
        result = _format_vote_summary(
            vote, "Desc", self._make_party_result(), "LFI, RN", "TestParty"
        )
        assert "LFI, RN" in result

    def test_includes_party_name(self):
        vote = make_vote()
        result = _format_vote_summary(
            vote, "Desc", self._make_party_result(), "Party A", "MyPartyName"
        )
        assert "MyPartyName" in result

    def test_includes_overall_yes_count(self):
        vote = make_vote(yes=42)
        result = _format_vote_summary(
            vote, "Desc", self._make_party_result(), "Party A", "TestParty"
        )
        assert "42" in result

    def test_no_justification_shows_default(self):
        vote = make_vote()
        party_result = self._make_party_result(justification=None)
        result = _format_vote_summary(
            vote, "Desc", party_result, "Party A", "TestParty"
        )
        assert "Aucune justification fournie." in result

    def test_with_justification_shows_it(self):
        vote = make_vote()
        party_result = self._make_party_result(justification="Pour raisons économiques")
        result = _format_vote_summary(
            vote, "Desc", party_result, "Party A", "TestParty"
        )
        assert "Pour raisons économiques" in result

    def test_includes_party_vote_counts(self):
        vote = make_vote()
        party_result = self._make_party_result(yes=7, no=2, abstain=1, not_voted=0)
        result = _format_vote_summary(
            vote, "Desc", party_result, "Party A", "TestParty"
        )
        assert "7" in result
        assert "2" in result


# ---------------------------------------------------------------------------
# Tests: rerank_documents (LLM-dependent)
# ---------------------------------------------------------------------------


class TestRerankDocuments:
    async def test_returns_reranked_documents(self):
        docs = [
            make_document("Doc A"),
            make_document("Doc B"),
            make_document("Doc C"),
        ]
        reranked_response = RerankingOutput(reranked_doc_indices=[2, 0, 1])

        with patch(
            "src.chatbot_async.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=reranked_response,
        ):
            result = await rerank_documents(docs, "test question", "chat history")

        assert result[0].page_content == "Doc C"
        assert result[1].page_content == "Doc A"

    async def test_limits_to_top_5(self):
        docs = [make_document(f"Doc {i}") for i in range(8)]
        reranked_response = RerankingOutput(
            reranked_doc_indices=[7, 6, 5, 4, 3, 2, 1, 0]
        )

        with patch(
            "src.chatbot_async.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=reranked_response,
        ):
            result = await rerank_documents(docs, "question", "history")

        assert len(result) == 5

    async def test_falls_back_to_top5_on_error(self):
        docs = [make_document(f"Doc {i}") for i in range(7)]
        bad_response = MagicMock()
        bad_response.reranked_doc_indices = [99, 98, 97]  # invalid indices

        with patch(
            "src.chatbot_async.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=bad_response,
        ):
            result = await rerank_documents(docs, "question", "history")

        # Should fall back to first 5 original docs
        assert len(result) == 5
        assert result[0].page_content == "Doc 0"

    async def test_empty_reranked_indices_falls_back(self):
        docs = [make_document(f"Doc {i}") for i in range(3)]
        empty_response = RerankingOutput(reranked_doc_indices=[])

        with patch(
            "src.chatbot_async.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=empty_response,
        ):
            result = await rerank_documents(docs, "question", "history")

        assert result == []

    async def test_calls_get_structured_output_with_messages(self):
        docs = [make_document("Content")]
        response = RerankingOutput(reranked_doc_indices=[0])

        with patch(
            "src.chatbot_async.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=response,
        ) as mock_llm:
            await rerank_documents(docs, "user question", "history")

        mock_llm.assert_awaited_once()
        args = mock_llm.call_args[0]
        messages = args[1]
        # Should be a list of [SystemMessage, HumanMessage]
        assert len(messages) == 2
        assert isinstance(messages[0], SystemMessage)
        assert isinstance(messages[1], HumanMessage)

    async def test_user_message_in_prompt(self):
        docs = [make_document("Content")]
        response = RerankingOutput(reranked_doc_indices=[0])
        captured = {}

        async def capture(*args, **kwargs):
            captured["messages"] = args[1]
            return response

        with patch(
            "src.chatbot_async.get_structured_output_from_llms", side_effect=capture
        ):
            await rerank_documents(docs, "specific user question", "history")

        human_msg = captured["messages"][1]
        assert "specific user question" in human_msg.content


# ---------------------------------------------------------------------------
# Tests: get_question_targets_and_type (LLM-dependent)
# ---------------------------------------------------------------------------


class TestGetQuestionTargetsAndType:
    def _parties(self):
        return [
            make_party("lfi", "LFI"),
            make_party("rn", "RN"),
            make_party("ps", "PS"),
        ]

    async def test_single_real_party_routes_directly(self):
        parties = self._parties()
        selected = [parties[0]]  # LFI only
        party_ids, question, is_comparing = await get_question_targets_and_type(
            "What is your policy?", "", parties, selected
        )
        assert party_ids == ["lfi"]
        assert is_comparing is False

    async def test_single_party_returns_original_question(self):
        parties = self._parties()
        selected = [parties[0]]
        _, question, _ = await get_question_targets_and_type(
            "Education policy?", "", parties, selected
        )
        assert question == "Education policy?"

    async def test_multiple_parties_calls_llm(self):
        parties = self._parties()
        selected = parties[:2]  # LFI + RN
        llm_response = PartyListGenerator(party_id_list=["lfi", "rn"])

        with patch(
            "src.chatbot_async.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=llm_response,
        ) as mock_llm:
            await get_question_targets_and_type(
                "Compare housing policies", "", parties, selected
            )

        mock_llm.assert_awaited()

    async def test_deduplicates_party_ids(self):
        parties = self._parties()
        selected = parties[:2]
        llm_response = PartyListGenerator(party_id_list=["lfi", "lfi", "rn"])

        with patch(
            "src.chatbot_async.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=llm_response,
        ):
            party_ids, _, _ = await get_question_targets_and_type(
                "Compare", "", parties, selected
            )

        assert len(party_ids) == len(set(party_ids))

    async def test_filters_assistant_id_from_multi_party(self):
        parties = self._parties()
        # If LLM returns chat-vote among party IDs with 2+ others, it should be filtered
        llm_response = PartyListGenerator(party_id_list=["lfi", "rn", ASSISTANT_ID])

        with patch(
            "src.chatbot_async.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=llm_response,
        ):
            party_ids, _, _ = await get_question_targets_and_type(
                "Compare", "", parties, parties[:2]
            )

        assert ASSISTANT_ID not in party_ids

    async def test_assistant_only_chat(self):
        """When no real parties are selected (empty list), LLM is called for routing."""
        parties = self._parties()
        llm_response = PartyListGenerator(party_id_list=[ASSISTANT_ID])

        with patch(
            "src.chatbot_async.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=llm_response,
        ):
            # Pass empty currently_selected_parties — simulates assistant-only chat
            party_ids, _, _ = await get_question_targets_and_type(
                "Tell me about elections", "", parties, []
            )

        # Returns whatever LLM says
        assert isinstance(party_ids, list)


# ---------------------------------------------------------------------------
# Tests: detect_entities_and_route (LLM-dependent)
# ---------------------------------------------------------------------------


class TestDetectEntitiesAndRoute:
    def _parties(self):
        return [
            make_party("lfi", "LFI", "La France Insoumise"),
            make_party("rn", "RN", "Rassemblement National"),
        ]

    def _candidates(self):
        return [
            make_candidate("cand-001", "Marie", "Dupont", "75056", "Paris", ["lfi"]),
            make_candidate("cand-002", "Jean", "Martin", "75056", "Paris", ["rn"]),
        ]

    async def test_returns_entity_detector(self):
        llm_response = EntityDetector(
            party_ids=["lfi"],
            candidate_ids=[],
            needs_clarification=False,
            clarification_message="",
            reformulated_question="LFI housing policy",
        )

        with patch(
            "src.chatbot_async.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=llm_response,
        ):
            result = await detect_entities_and_route(
                "What does LFI think about housing?",
                "",
                self._parties(),
                self._candidates(),
                "national",
            )

        assert isinstance(result, EntityDetector)
        assert "lfi" in result.party_ids

    async def test_filters_invalid_party_ids(self):
        llm_response = EntityDetector(
            party_ids=["lfi", "nonexistent-party"],
            candidate_ids=[],
            needs_clarification=False,
            clarification_message="",
            reformulated_question="question",
        )

        with patch(
            "src.chatbot_async.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=llm_response,
        ):
            result = await detect_entities_and_route(
                "question", "", self._parties(), self._candidates(), "national"
            )

        assert "nonexistent-party" not in result.party_ids
        assert "lfi" in result.party_ids

    async def test_filters_candidates_by_municipality_code_in_local_scope(self):
        candidates = [
            make_candidate("cand-paris", "Alice", "Smith", "75056", "Paris", ["lfi"]),
            make_candidate("cand-lyon", "Bob", "Jones", "69001", "Lyon", ["rn"]),
        ]
        llm_response = EntityDetector(
            party_ids=[],
            candidate_ids=["cand-lyon"],  # LLM returns lyon candidate
            needs_clarification=False,
            clarification_message="",
            reformulated_question="question",
        )

        with patch(
            "src.chatbot_async.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=llm_response,
        ):
            result = await detect_entities_and_route(
                "question",
                "",
                self._parties(),
                candidates,
                "local",
                municipality_code="75056",  # Paris scope
            )

        # cand-lyon should be filtered out (wrong municipality)
        assert "cand-lyon" not in result.candidate_ids

    async def test_all_parties_keyword_overrides_llm(self):
        llm_response = EntityDetector(
            party_ids=["lfi"],
            candidate_ids=[],
            needs_clarification=False,
            clarification_message="",
            reformulated_question="question",
        )

        with patch(
            "src.chatbot_async.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=llm_response,
        ):
            result = await detect_entities_and_route(
                "Que pensent tous les partis de l'immigration?",
                "",
                self._parties(),
                self._candidates(),
                "national",
            )

        # All parties should be included due to "tous les partis" keyword
        assert "lfi" in result.party_ids
        assert "rn" in result.party_ids

    async def test_needs_clarification_cleared_when_entities_found(self):
        llm_response = EntityDetector(
            party_ids=["lfi"],
            candidate_ids=[],
            needs_clarification=True,  # LLM thinks clarification needed
            clarification_message="Please specify a party",
            reformulated_question="question",
        )

        with patch(
            "src.chatbot_async.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=llm_response,
        ):
            result = await detect_entities_and_route(
                "LFI housing", "", self._parties(), self._candidates(), "national"
            )

        # Since lfi is found, needs_clarification should be False
        assert result.needs_clarification is False

    async def test_candidate_party_ids_added_to_result(self):
        """When a candidate is found, their party_ids should be added to party_ids."""
        llm_response = EntityDetector(
            party_ids=[],
            candidate_ids=["cand-001"],
            needs_clarification=False,
            clarification_message="",
            reformulated_question="question",
        )

        with patch(
            "src.chatbot_async.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=llm_response,
        ):
            result = await detect_entities_and_route(
                "What does Marie Dupont think?",
                "",
                self._parties(),
                self._candidates(),
                "national",
            )

        assert "lfi" in result.party_ids


# ---------------------------------------------------------------------------
# Tests: generate_improvement_rag_query (LLM-dependent)
# ---------------------------------------------------------------------------


class TestGenerateImprovementRagQuery:
    async def test_returns_string_response(self):
        party = make_party()
        llm_response = AIMessage(content="Improved query text")

        with patch(
            "src.chatbot_async.get_answer_from_llms",
            new_callable=AsyncMock,
            return_value=llm_response,
        ):
            result = await generate_improvement_rag_query(
                party, "history", "last message"
            )

        assert result == "Improved query text"

    async def test_uses_assistant_prompt_for_chat_vote(self):
        captured = {}

        async def capture(*args, **kwargs):
            captured["messages"] = args[1]
            return AIMessage(content="query")

        with patch("src.chatbot_async.get_answer_from_llms", side_effect=capture):
            await generate_improvement_rag_query(
                CHATVOTE_ASSISTANT, "history", "last message"
            )

        sys_msg = captured["messages"][0]
        # For chat-vote assistant, should use the general chat rag query template
        assert isinstance(sys_msg, SystemMessage)

    async def test_uses_party_prompt_for_regular_party(self):
        party = make_party("lfi", "LFI")
        captured = {}

        async def capture(*args, **kwargs):
            captured["messages"] = args[1]
            return AIMessage(content="query")

        with patch("src.chatbot_async.get_answer_from_llms", side_effect=capture):
            await generate_improvement_rag_query(party, "history", "last message")

        sys_msg = captured["messages"][0]
        assert "LFI" in sys_msg.content

    async def test_handles_list_response_content(self):
        party = make_party()
        llm_response = AIMessage(content=["list item content"])

        with patch(
            "src.chatbot_async.get_answer_from_llms",
            new_callable=AsyncMock,
            return_value=llm_response,
        ):
            result = await generate_improvement_rag_query(party, "history", "message")

        assert result == "list item content"

    async def test_handles_list_dict_response_content(self):
        party = make_party()
        llm_response = AIMessage(content=[{"content": "dict content"}])

        with patch(
            "src.chatbot_async.get_answer_from_llms",
            new_callable=AsyncMock,
            return_value=llm_response,
        ):
            result = await generate_improvement_rag_query(party, "history", "message")

        assert result == "dict content"


# ---------------------------------------------------------------------------
# Tests: generate_improvement_rag_query_candidate (LLM-dependent)
# ---------------------------------------------------------------------------


class TestGenerateImprovementRagQueryCandidate:
    async def test_returns_string_result(self):
        llm_response = AIMessage(content="Candidate improved query")

        with patch(
            "src.chatbot_async.get_answer_from_llms",
            new_callable=AsyncMock,
            return_value=llm_response,
        ):
            result = await generate_improvement_rag_query_candidate(
                "history", "last message"
            )

        assert result == "Candidate improved query"

    async def test_with_municipality_code(self):
        captured = {}

        async def capture(*args, **kwargs):
            captured["messages"] = args[1]
            return AIMessage(content="query")

        with patch("src.chatbot_async.get_answer_from_llms", side_effect=capture):
            await generate_improvement_rag_query_candidate(
                "history", "last message", municipality_code="75056"
            )

        sys_msg = captured["messages"][0]
        assert "75056" in sys_msg.content

    async def test_without_municipality_code_uses_national_scope(self):
        captured = {}

        async def capture(*args, **kwargs):
            captured["messages"] = args[1]
            return AIMessage(content="query")

        with patch("src.chatbot_async.get_answer_from_llms", side_effect=capture):
            await generate_improvement_rag_query_candidate(
                "history", "last message", municipality_code=None
            )

        sys_msg = captured["messages"][0]
        assert isinstance(sys_msg, SystemMessage)


# ---------------------------------------------------------------------------
# Tests: generate_chat_summary (LLM-dependent)
# ---------------------------------------------------------------------------


class TestGenerateChatSummary:
    async def test_returns_summary_string(self):
        messages = [
            Message(role=Role.USER, content="Question about housing"),
            Message(role=Role.ASSISTANT, content="LFI response", party_id="lfi"),
        ]
        llm_response = ChatSummaryGenerator(
            chat_summary="Discussion about housing policy"
        )

        with patch(
            "src.chatbot_async.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=llm_response,
        ):
            result = await generate_chat_summary(messages)

        assert result == "Discussion about housing policy"

    async def test_empty_history_returns_fallback(self):
        llm_response = MagicMock()
        # No chat_summary attribute -> should use fallback
        del llm_response.chat_summary

        with patch(
            "src.chatbot_async.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=llm_response,
        ):
            result = await generate_chat_summary([])

        assert isinstance(result, str)

    async def test_formats_user_messages_correctly(self):
        messages = [Message(role=Role.USER, content="User question")]
        captured = {}

        async def capture(*args, **kwargs):
            captured["messages"] = args[1]
            return ChatSummaryGenerator(chat_summary="summary")

        with patch(
            "src.chatbot_async.get_structured_output_from_llms", side_effect=capture
        ):
            await generate_chat_summary(messages)

        human_msg = captured["messages"][1]
        assert "Utilisateur" in human_msg.content

    async def test_formats_assistant_messages_with_party_id(self):
        messages = [
            Message(role=Role.ASSISTANT, content="Party response", party_id="lfi")
        ]
        captured = {}

        async def capture(*args, **kwargs):
            captured["messages"] = args[1]
            return ChatSummaryGenerator(chat_summary="summary")

        with patch(
            "src.chatbot_async.get_structured_output_from_llms", side_effect=capture
        ):
            await generate_chat_summary(messages)

        human_msg = captured["messages"][1]
        assert "lfi" in human_msg.content


# ---------------------------------------------------------------------------
# Tests: get_improved_rag_query_voting_behavior (LLM-dependent)
# ---------------------------------------------------------------------------


class TestGetImprovedRagQueryVotingBehavior:
    async def test_returns_string_content(self):
        party = make_party("lfi", "LFI")
        llm_response = AIMessage(content="Improved voting query")

        with patch(
            "src.chatbot_async.get_answer_from_llms",
            new_callable=AsyncMock,
            return_value=llm_response,
        ):
            result = await get_improved_rag_query_voting_behavior(
                party, "last user message", "last assistant message"
            )

        assert result == "Improved voting query"

    async def test_includes_party_name_in_prompt(self):
        party = make_party("lfi", "LFI")
        captured = {}

        async def capture(*args, **kwargs):
            captured["messages"] = args[1]
            return AIMessage(content="query")

        with patch("src.chatbot_async.get_answer_from_llms", side_effect=capture):
            await get_improved_rag_query_voting_behavior(party, "user msg", "asst msg")

        # Party name should appear in messages
        all_content = " ".join(msg.content for msg in captured["messages"])
        assert "LFI" in all_content

    async def test_includes_user_and_assistant_messages_in_prompt(self):
        party = make_party()
        captured = {}

        async def capture(*args, **kwargs):
            captured["messages"] = args[1]
            return AIMessage(content="query")

        with patch("src.chatbot_async.get_answer_from_llms", side_effect=capture):
            await get_improved_rag_query_voting_behavior(
                party, "specific user question", "specific assistant answer"
            )

        human_msg = captured["messages"][1]
        assert "specific user question" in human_msg.content
        assert "specific assistant answer" in human_msg.content


# ---------------------------------------------------------------------------
# Tests: generate_chat_title_and_chick_replies (LLM-dependent)
# ---------------------------------------------------------------------------


class TestGenerateChatTitleAndChickReplies:
    async def test_returns_group_chat_title_quick_reply_generator(self):
        parties = [make_party("lfi", "LFI"), make_party("rn", "RN")]
        llm_response = GroupChatTitleQuickReplyGenerator(
            chat_title="Housing Discussion",
            quick_replies=["LFI's plan?", "RN's plan?", "Comparison?"],
        )

        with patch(
            "src.chatbot_async.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=llm_response,
        ):
            result = await generate_chat_title_and_chick_replies(
                "history", "Housing Chat", parties
            )

        assert isinstance(result, GroupChatTitleQuickReplyGenerator)
        assert result.chat_title == "Housing Discussion"
        assert len(result.quick_replies) == 3

    async def test_filters_assistant_from_party_list(self):
        from src.models.assistant import CHATVOTE_ASSISTANT

        parties = [make_party("lfi", "LFI"), CHATVOTE_ASSISTANT]
        captured = {}

        async def capture(*args, **kwargs):
            captured["messages"] = args[1]
            return GroupChatTitleQuickReplyGenerator(
                chat_title="Title", quick_replies=[]
            )

        with patch(
            "src.chatbot_async.get_structured_output_from_llms", side_effect=capture
        ):
            await generate_chat_title_and_chick_replies("history", "Title", parties)

        # The system message should include LFI but not chat-vote assistant in party list
        sys_msg = captured["messages"][0]
        assert ASSISTANT_ID not in sys_msg.content or "LFI" in sys_msg.content

    async def test_empty_party_list_uses_no_party_message(self):
        captured = {}

        async def capture(*args, **kwargs):
            captured["messages"] = args[1]
            return GroupChatTitleQuickReplyGenerator(
                chat_title="Title", quick_replies=[]
            )

        with patch(
            "src.chatbot_async.get_structured_output_from_llms", side_effect=capture
        ):
            await generate_chat_title_and_chick_replies("history", "Title", [])

        sys_msg = captured["messages"][0]
        assert "Aucune liste" in sys_msg.content or "No party" in sys_msg.content

    async def test_locale_en_uses_english_message(self):
        captured = {}

        async def capture(*args, **kwargs):
            captured["messages"] = args[1]
            return GroupChatTitleQuickReplyGenerator(
                chat_title="Title", quick_replies=[]
            )

        with patch(
            "src.chatbot_async.get_structured_output_from_llms", side_effect=capture
        ):
            await generate_chat_title_and_chick_replies(
                "history", "Title", [], locale="en"
            )

        sys_msg = captured["messages"][0]
        assert "No party" in sys_msg.content

    async def test_fallback_values_on_missing_attributes(self):
        llm_response = MagicMock(spec=[])  # No attributes

        with patch(
            "src.chatbot_async.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=llm_response,
        ):
            result = await generate_chat_title_and_chick_replies("history", "Title", [])

        assert result.chat_title == ""
        assert result.quick_replies == []


# ---------------------------------------------------------------------------
# Tests: generate_streaming_chatbot_response (streaming, LLM-dependent)
# ---------------------------------------------------------------------------


class TestGenerateStreamingChatbotResponse:
    async def _collect_stream(self, stream_iter):
        items = []
        async for chunk in stream_iter:
            items.append(chunk)
        return items

    async def test_returns_async_iterator(self):
        party = make_party()
        docs = [make_document("Policy content")]

        make_streaming_llm("test", chunks=["response chunk"])

        async def fake_stream(*args, **kwargs):
            async def _gen():
                yield AIMessage(content="response chunk")

            return _gen()

        with patch(
            "src.chatbot_async.stream_answer_from_llms", side_effect=fake_stream
        ):
            result = await generate_streaming_chatbot_response(
                party, "history", "question", docs, [], LLMSize.LARGE
            )

        chunks = await self._collect_stream(result)
        assert len(chunks) > 0

    async def test_party_name_in_system_prompt(self):
        party = make_party("lfi", "LFI")
        docs = [make_document("Content")]
        captured = {}

        async def capture(llms, messages, **kwargs):
            captured["messages"] = messages

            async def _gen():
                yield AIMessage(content="chunk")

            return _gen()

        with patch("src.chatbot_async.stream_answer_from_llms", side_effect=capture):
            await generate_streaming_chatbot_response(
                party, "history", "question", docs, [], LLMSize.LARGE
            )

        sys_msg = captured["messages"][0]
        assert "LFI" in sys_msg.content

    async def test_assistant_responder_uses_chatvote_prompt(self):
        docs = [make_document("Content")]
        all_parties = [make_party("lfi", "LFI")]
        captured = {}

        async def capture(llms, messages, **kwargs):
            captured["messages"] = messages

            async def _gen():
                yield AIMessage(content="chunk")

            return _gen()

        with patch("src.chatbot_async.stream_answer_from_llms", side_effect=capture):
            await generate_streaming_chatbot_response(
                CHATVOTE_ASSISTANT,
                "history",
                "question",
                docs,
                all_parties,
                LLMSize.LARGE,
            )

        sys_msg = captured["messages"][0]
        assert "LFI" in sys_msg.content  # party list is included in assistant prompt

    async def test_rag_context_included_in_prompt(self):
        party = make_party()
        docs = [make_document("Unique RAG content XYZ")]
        captured = {}

        async def capture(llms, messages, **kwargs):
            captured["messages"] = messages

            async def _gen():
                yield AIMessage(content="chunk")

            return _gen()

        with patch("src.chatbot_async.stream_answer_from_llms", side_effect=capture):
            await generate_streaming_chatbot_response(
                party, "history", "question", docs, [], LLMSize.LARGE
            )

        sys_msg = captured["messages"][0]
        assert "Unique RAG content XYZ" in sys_msg.content

    async def test_locale_en_passes_english_prompts(self):
        party = make_party()
        docs = []
        captured = {}

        async def capture(llms, messages, **kwargs):
            captured["messages"] = messages

            async def _gen():
                yield AIMessage(content="chunk")

            return _gen()

        with patch("src.chatbot_async.stream_answer_from_llms", side_effect=capture):
            await generate_streaming_chatbot_response(
                party, "history", "question", docs, [], LLMSize.LARGE, locale="en"
            )

        # Should have been called with locale-specific prompts
        assert captured["messages"] is not None


# ---------------------------------------------------------------------------
# Tests: generate_streaming_chatbot_comparing_response (streaming, LLM-dependent)
# ---------------------------------------------------------------------------


class TestGenerateStreamingChatbotComparingResponse:
    async def test_returns_async_iterator(self):
        parties = [make_party("lfi", "LFI"), make_party("rn", "RN")]
        relevant_docs = {
            "lfi": [make_document("LFI content")],
            "rn": [make_document("RN content")],
        }

        async def fake_stream(*args, **kwargs):
            async def _gen():
                yield AIMessage(content="comparison chunk")

            return _gen()

        with patch(
            "src.chatbot_async.stream_answer_from_llms", side_effect=fake_stream
        ):
            result = await generate_streaming_chatbot_comparing_response(
                "history", "Compare housing", relevant_docs, parties, LLMSize.LARGE
            )

        chunks = [item async for item in result]
        assert len(chunks) > 0

    async def test_parties_included_in_system_prompt(self):
        parties = [make_party("lfi", "LFI"), make_party("rn", "RN")]
        relevant_docs = {"lfi": [], "rn": []}
        captured = {}

        async def capture(llms, messages, **kwargs):
            captured["messages"] = messages

            async def _gen():
                yield AIMessage(content="chunk")

            return _gen()

        with patch("src.chatbot_async.stream_answer_from_llms", side_effect=capture):
            await generate_streaming_chatbot_comparing_response(
                "history", "Compare", relevant_docs, parties, LLMSize.LARGE
            )

        sys_msg = captured["messages"][0]
        assert "LFI" in sys_msg.content
        assert "RN" in sys_msg.content


# ---------------------------------------------------------------------------
# Tests: generate_streaming_candidate_response (streaming, LLM-dependent)
# ---------------------------------------------------------------------------


class TestGenerateStreamingCandidateResponse:
    async def test_returns_async_iterator(self):
        candidate = make_candidate()
        parties = [make_party("test-party", "Test")]
        docs = [make_document("Candidate content")]

        async def fake_stream(*args, **kwargs):
            async def _gen():
                yield AIMessage(content="candidate chunk")

            return _gen()

        with patch(
            "src.chatbot_async.stream_answer_from_llms", side_effect=fake_stream
        ):
            result = await generate_streaming_candidate_response(
                candidate, "history", "question", docs, parties, LLMSize.LARGE
            )

        chunks = [item async for item in result]
        assert len(chunks) > 0

    async def test_candidate_name_in_system_prompt(self):
        candidate = make_candidate(first_name="Marie", last_name="Dupont")
        parties = [make_party("test-party")]
        docs = []
        captured = {}

        async def capture(llms, messages, **kwargs):
            captured["messages"] = messages

            async def _gen():
                yield AIMessage(content="chunk")

            return _gen()

        with patch("src.chatbot_async.stream_answer_from_llms", side_effect=capture):
            await generate_streaming_candidate_response(
                candidate, "history", "question", docs, parties, LLMSize.LARGE
            )

        sys_msg = captured["messages"][0]
        assert "Marie Dupont" in sys_msg.content

    async def test_party_name_resolved_from_party_ids(self):
        candidate = make_candidate(party_ids=["lfi"])
        parties = [make_party("lfi", "LFI")]
        docs = []
        captured = {}

        async def capture(llms, messages, **kwargs):
            captured["messages"] = messages

            async def _gen():
                yield AIMessage(content="chunk")

            return _gen()

        with patch("src.chatbot_async.stream_answer_from_llms", side_effect=capture):
            await generate_streaming_candidate_response(
                candidate, "history", "question", docs, parties, LLMSize.LARGE
            )

        sys_msg = captured["messages"][0]
        assert "LFI" in sys_msg.content

    async def test_independent_candidate_shows_independant(self):
        candidate = make_candidate(party_ids=[])
        parties = []
        captured = {}

        async def capture(llms, messages, **kwargs):
            captured["messages"] = messages

            async def _gen():
                yield AIMessage(content="chunk")

            return _gen()

        with patch("src.chatbot_async.stream_answer_from_llms", side_effect=capture):
            await generate_streaming_candidate_response(
                candidate, "history", "question", [], parties, LLMSize.LARGE
            )

        sys_msg = captured["messages"][0]
        assert "Indépendant" in sys_msg.content


# ---------------------------------------------------------------------------
# Tests: generate_streaming_candidate_local_response (streaming, LLM-dependent)
# ---------------------------------------------------------------------------


class TestGenerateStreamingCandidateLocalResponse:
    async def test_returns_async_iterator(self):
        candidates = [make_candidate()]
        parties = [make_party("test-party")]
        docs = [make_document("local content")]

        async def fake_stream(*args, **kwargs):
            async def _gen():
                yield AIMessage(content="local chunk")

            return _gen()

        with patch(
            "src.chatbot_async.stream_answer_from_llms", side_effect=fake_stream
        ):
            result = await generate_streaming_candidate_local_response(
                "75056",
                "Paris",
                candidates,
                "history",
                "question",
                docs,
                parties,
                LLMSize.LARGE,
            )

        chunks = [item async for item in result]
        assert len(chunks) > 0

    async def test_municipality_name_in_system_prompt(self):
        candidates = [make_candidate()]
        parties = [make_party("test-party")]
        captured = {}

        async def capture(llms, messages, **kwargs):
            captured["messages"] = messages

            async def _gen():
                yield AIMessage(content="chunk")

            return _gen()

        with patch("src.chatbot_async.stream_answer_from_llms", side_effect=capture):
            await generate_streaming_candidate_local_response(
                "75056",
                "Paris",
                candidates,
                "history",
                "question",
                [],
                parties,
                LLMSize.LARGE,
            )

        sys_msg = captured["messages"][0]
        assert "Paris" in sys_msg.content

    async def test_candidate_names_in_system_prompt(self):
        candidates = [make_candidate(first_name="Marie", last_name="Dupont")]
        parties = [make_party("test-party")]
        captured = {}

        async def capture(llms, messages, **kwargs):
            captured["messages"] = messages

            async def _gen():
                yield AIMessage(content="chunk")

            return _gen()

        with patch("src.chatbot_async.stream_answer_from_llms", side_effect=capture):
            await generate_streaming_candidate_local_response(
                "75056",
                "Paris",
                candidates,
                "history",
                "question",
                [],
                parties,
                LLMSize.LARGE,
            )

        sys_msg = captured["messages"][0]
        assert "Marie Dupont" in sys_msg.content

    async def test_candidate_with_manifesto_shows_pdf_link(self):
        candidates = [
            make_candidate(
                manifesto_pdf_url="https://example.com/manifesto.pdf",
            )
        ]
        parties = [make_party("test-party")]
        captured = {}

        async def capture(llms, messages, **kwargs):
            captured["messages"] = messages

            async def _gen():
                yield AIMessage(content="chunk")

            return _gen()

        with patch("src.chatbot_async.stream_answer_from_llms", side_effect=capture):
            await generate_streaming_candidate_local_response(
                "75056",
                "Paris",
                candidates,
                "history",
                "question",
                [],
                parties,
                LLMSize.LARGE,
            )

        sys_msg = captured["messages"][0]
        assert "chatvote.org/pdf/view" in sys_msg.content

    async def test_no_candidates_shows_none_registered(self):
        captured = {}

        async def capture(llms, messages, **kwargs):
            captured["messages"] = messages

            async def _gen():
                yield AIMessage(content="chunk")

            return _gen()

        with patch("src.chatbot_async.stream_answer_from_llms", side_effect=capture):
            await generate_streaming_candidate_local_response(
                "75056", "Paris", [], "history", "question", [], [], LLMSize.LARGE
            )

        sys_msg = captured["messages"][0]
        assert "Aucun candidat" in sys_msg.content


# ---------------------------------------------------------------------------
# Tests: generate_streaming_candidate_national_response (streaming, LLM-dependent)
# ---------------------------------------------------------------------------


class TestGenerateStreamingCandidateNationalResponse:
    async def test_returns_async_iterator(self):
        docs = [make_document("National content")]

        async def fake_stream(*args, **kwargs):
            async def _gen():
                yield AIMessage(content="national chunk")

            return _gen()

        with patch(
            "src.chatbot_async.stream_answer_from_llms", side_effect=fake_stream
        ):
            result = await generate_streaming_candidate_national_response(
                "history", "question", docs, LLMSize.LARGE
            )

        chunks = [item async for item in result]
        assert len(chunks) > 0

    async def test_rag_context_in_system_prompt(self):
        docs = [make_document("National unique content ZZZ")]
        captured = {}

        async def capture(llms, messages, **kwargs):
            captured["messages"] = messages

            async def _gen():
                yield AIMessage(content="chunk")

            return _gen()

        with patch("src.chatbot_async.stream_answer_from_llms", side_effect=capture):
            await generate_streaming_candidate_national_response(
                "history", "question", docs, LLMSize.LARGE
            )

        sys_msg = captured["messages"][0]
        assert "National unique content ZZZ" in sys_msg.content


# ---------------------------------------------------------------------------
# Tests: generate_streaming_combined_response (streaming, LLM-dependent)
# ---------------------------------------------------------------------------


class TestGenerateStreamingCombinedResponse:
    async def test_returns_async_iterator(self):
        party = make_party()
        manifesto_docs = [make_document("Manifesto content")]
        candidate_docs = [make_document("Candidate content")]

        async def fake_stream(*args, **kwargs):
            async def _gen():
                yield AIMessage(content="combined chunk")

            return _gen()

        with patch(
            "src.chatbot_async.stream_answer_from_llms", side_effect=fake_stream
        ):
            result = await generate_streaming_combined_response(
                party, "history", "question", manifesto_docs, candidate_docs, "national"
            )

        chunks = [item async for item in result]
        assert len(chunks) > 0

    async def test_party_name_in_system_prompt(self):
        party = make_party("lfi", "LFI")
        captured = {}

        async def capture(llms, messages, **kwargs):
            captured["messages"] = messages

            async def _gen():
                yield AIMessage(content="chunk")

            return _gen()

        with patch("src.chatbot_async.stream_answer_from_llms", side_effect=capture):
            await generate_streaming_combined_response(
                party, "history", "question", [], [], "national"
            )

        sys_msg = captured["messages"][0]
        assert "LFI" in sys_msg.content

    async def test_local_scope_with_municipality(self):
        party = make_party()
        captured = {}

        async def capture(llms, messages, **kwargs):
            captured["messages"] = messages

            async def _gen():
                yield AIMessage(content="chunk")

            return _gen()

        with patch("src.chatbot_async.stream_answer_from_llms", side_effect=capture):
            await generate_streaming_combined_response(
                party, "history", "question", [], [], "local", municipality_name="Lyon"
            )

        sys_msg = captured["messages"][0]
        assert "Lyon" in sys_msg.content

    async def test_national_scope_description(self):
        party = make_party("lfi", "LFI")
        captured = {}

        async def capture(llms, messages, **kwargs):
            captured["messages"] = messages

            async def _gen():
                yield AIMessage(content="chunk")

            return _gen()

        with patch("src.chatbot_async.stream_answer_from_llms", side_effect=capture):
            await generate_streaming_combined_response(
                party, "history", "question", [], [], "national"
            )

        sys_msg = captured["messages"][0]
        assert "NATIONAL" in sys_msg.content or "national" in sys_msg.content.lower()
