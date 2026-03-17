# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Comprehensive unit tests for all Pydantic models in the ChatVote backend.

Groups:
  - LLMSize / LLM                (src/models/general.py)
  - Party                        (src/models/party.py)
  - Candidate                    (src/models/candidate.py)
  - Role / Message / ChatSession / ProConAssessment
    / GroupChatSession / CachedResponse  (src/models/chat.py)
  - Assistant / CHATVOTE_ASSISTANT / ASSISTANT_ID  (src/models/assistant.py)
  - Link / VotingResultsOverall / VotingResultsByParty
    / VotingResults / Vote       (src/models/vote.py)
  - All DTOs                     (src/models/dtos.py)
  - Structured outputs           (src/models/structured_outputs.py)
  - Fiabilite / ChunkMetadata / THEME_TAXONOMY
    / _infer_fiabilite            (src/models/chunk_metadata.py)
  - ScrapedPage / ScrapedWebsite (src/models/scraper.py)
"""

import sys

# Evict mocks set by other test files (e.g. test_aiohttp_app.py) so real modules load
sys.modules.pop("src.models.chunk_metadata", None)

from datetime import datetime  # noqa: E402

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

# ---------------------------------------------------------------------------
# src/models/general.py
# ---------------------------------------------------------------------------


class TestLLMSize:
    def test_values(self):
        from src.models.general import LLMSize

        assert LLMSize.SMALL == "small"
        assert LLMSize.LARGE == "large"

    def test_is_str_enum(self):
        from src.models.general import LLMSize

        assert isinstance(LLMSize.SMALL, str)
        assert isinstance(LLMSize.LARGE, str)

    def test_all_members(self):
        from src.models.general import LLMSize

        members = {m.value for m in LLMSize}
        assert members == {"small", "large"}


class TestLLM:
    def _fake_llm(self, responses=None):
        from langchain_core.language_models.fake_chat_models import FakeListChatModel

        return FakeListChatModel(responses=responses or ["ok"])

    def test_valid_required_fields(self):
        from src.models.general import LLM, LLMSize

        llm = LLM(
            name="test-model",
            model=self._fake_llm(),
            sizes=[LLMSize.LARGE],
            priority=1,
            user_capacity_per_minute=100,
            is_at_rate_limit=False,
        )
        assert llm.name == "test-model"
        assert llm.priority == 1
        assert llm.user_capacity_per_minute == 100
        assert llm.is_at_rate_limit is False

    def test_defaults(self):
        from src.models.general import LLM, LLMSize

        llm = LLM(
            name="x",
            model=self._fake_llm(),
            sizes=[LLMSize.SMALL],
            priority=5,
            user_capacity_per_minute=50,
            is_at_rate_limit=True,
        )
        assert llm.premium_only is False
        assert llm.back_up_only is False

    def test_all_fields(self):
        from src.models.general import LLM, LLMSize

        llm = LLM(
            name="premium-model",
            model=self._fake_llm(),
            sizes=[LLMSize.SMALL, LLMSize.LARGE],
            priority=10,
            user_capacity_per_minute=200,
            is_at_rate_limit=True,
            premium_only=True,
            back_up_only=True,
        )
        assert llm.premium_only is True
        assert llm.back_up_only is True
        assert len(llm.sizes) == 2

    def test_sizes_list(self):
        from src.models.general import LLM, LLMSize

        llm = LLM(
            name="multi",
            model=self._fake_llm(),
            sizes=[LLMSize.SMALL, LLMSize.LARGE],
            priority=1,
            user_capacity_per_minute=10,
            is_at_rate_limit=False,
        )
        assert LLMSize.SMALL in llm.sizes
        assert LLMSize.LARGE in llm.sizes

    def test_model_dump_contains_name(self):
        from src.models.general import LLM, LLMSize

        llm = LLM(
            name="dump-test",
            model=self._fake_llm(),
            sizes=[LLMSize.LARGE],
            priority=2,
            user_capacity_per_minute=30,
            is_at_rate_limit=False,
        )
        d = llm.model_dump()
        assert d["name"] == "dump-test"
        assert d["priority"] == 2


# ---------------------------------------------------------------------------
# src/models/party.py
# ---------------------------------------------------------------------------


class TestParty:
    def test_valid_required_fields(self, party_factory):
        party = party_factory()
        assert party.party_id == "test-party"
        assert party.name == "Test Party"
        assert party.long_name == "The Test Party"
        assert party.description == "A test party"
        assert party.website_url == "https://test-party.fr"
        assert party.candidate == "Jean Test"
        assert party.election_manifesto_url == "https://test-party.fr/manifesto.pdf"

    def test_defaults(self, party_factory):
        party = party_factory()
        assert party.logo_url == ""
        assert party.candidate_image_url == ""
        assert party.background_color == "#4A90D9"
        assert party.is_small_party is False
        assert party.is_already_in_parliament is False

    def test_all_fields(self, party_factory):
        party = party_factory(
            logo_url="https://logo.png",
            candidate_image_url="https://photo.jpg",
            background_color="#FF0000",
            is_small_party=True,
            is_already_in_parliament=True,
        )
        assert party.logo_url == "https://logo.png"
        assert party.candidate_image_url == "https://photo.jpg"
        assert party.background_color == "#FF0000"
        assert party.is_small_party is True
        assert party.is_already_in_parliament is True

    def test_missing_required_field_raises(self):
        from src.models.party import Party

        with pytest.raises(ValidationError):
            Party(
                name="Missing",
                long_name="Missing Long",
                description="desc",
                website_url="https://example.fr",
                candidate="Someone",
                election_manifesto_url="https://example.fr/manifesto.pdf",
                # party_id missing
            )

    def test_model_dump(self, party_factory):
        party = party_factory(party_id="lfi", name="LFI")
        d = party.model_dump()
        assert d["party_id"] == "lfi"
        assert d["name"] == "LFI"
        assert "background_color" in d


# ---------------------------------------------------------------------------
# src/models/candidate.py
# ---------------------------------------------------------------------------


class TestCandidate:
    def test_valid_required_fields(self, candidate_factory):
        cand = candidate_factory()
        assert cand.candidate_id == "cand-001"
        assert cand.first_name == "Marie"
        assert cand.last_name == "Dupont"
        assert cand.election_type_id == "municipales-2026"

    def test_defaults(self, candidate_factory):
        cand = candidate_factory()
        assert cand.municipality_code is None
        assert cand.municipality_name is None
        assert cand.party_ids == []
        assert cand.presence_score == 0
        assert cand.position is None
        assert cand.bio is None
        assert cand.is_incumbent is False
        assert cand.birth_year is None
        assert cand.photo_url is None
        assert cand.contact_email is None
        assert cand.website_url is None
        assert cand.manifesto_pdf_url is None
        assert cand.created_at is None
        assert cand.updated_at is None

    def test_all_fields(self, candidate_factory):
        now = datetime(2026, 1, 1)
        cand = candidate_factory(
            municipality_code="75056",
            municipality_name="Paris",
            party_ids=["ps", "eelv"],
            presence_score=85,
            position="Tête de liste",
            bio="Un candidat sérieux.",
            is_incumbent=True,
            birth_year=1975,
            photo_url="https://photo.jpg",
            contact_email="marie@example.fr",
            website_url="https://marie.fr",
            manifesto_pdf_url="https://marie.fr/manifesto.pdf",
            created_at=now,
            updated_at=now,
        )
        assert cand.municipality_code == "75056"
        assert cand.municipality_name == "Paris"
        assert cand.party_ids == ["ps", "eelv"]
        assert cand.presence_score == 85
        assert cand.position == "Tête de liste"
        assert cand.bio == "Un candidat sérieux."
        assert cand.is_incumbent is True
        assert cand.birth_year == 1975
        assert cand.photo_url == "https://photo.jpg"
        assert cand.contact_email == "marie@example.fr"
        assert cand.website_url == "https://marie.fr"
        assert cand.manifesto_pdf_url == "https://marie.fr/manifesto.pdf"
        assert cand.created_at == now
        assert cand.updated_at == now

    def test_missing_required_raises(self):
        from src.models.candidate import Candidate

        with pytest.raises(ValidationError):
            Candidate(
                first_name="Jean",
                last_name="Doe",
                # candidate_id and election_type_id missing
            )

    # Properties

    def test_full_name(self, candidate_factory):
        cand = candidate_factory(first_name="Marie", last_name="Dupont")
        assert cand.full_name == "Marie Dupont"

    def test_is_in_coalition_false_when_single_party(self, candidate_factory):
        cand = candidate_factory(party_ids=["ps"])
        assert cand.is_in_coalition is False

    def test_is_in_coalition_false_when_no_party(self, candidate_factory):
        cand = candidate_factory(party_ids=[])
        assert cand.is_in_coalition is False

    def test_is_in_coalition_true_when_multiple_parties(self, candidate_factory):
        cand = candidate_factory(party_ids=["ps", "eelv"])
        assert cand.is_in_coalition is True

    def test_is_national_candidate_true(self, candidate_factory):
        cand = candidate_factory(municipality_code=None)
        assert cand.is_national_candidate is True

    def test_is_national_candidate_false(self, candidate_factory):
        cand = candidate_factory(municipality_code="75056")
        assert cand.is_national_candidate is False

    def test_model_dump(self, candidate_factory):
        cand = candidate_factory()
        d = cand.model_dump()
        assert d["candidate_id"] == "cand-001"
        assert d["first_name"] == "Marie"
        assert d["last_name"] == "Dupont"


# ---------------------------------------------------------------------------
# src/models/chat.py
# ---------------------------------------------------------------------------


class TestRole:
    def test_values(self):
        from src.models.chat import Role

        assert Role.USER == "user"
        assert Role.ASSISTANT == "assistant"

    def test_is_str_enum(self):
        from src.models.chat import Role

        assert isinstance(Role.USER, str)

    def test_all_members(self):
        from src.models.chat import Role

        members = {m.value for m in Role}
        assert members == {"user", "assistant"}


class TestMessage:
    def test_valid_required_fields(self, message_factory):
        msg = message_factory()
        assert msg.role.value == "user"
        assert msg.content == "Question de test"

    def test_defaults(self, message_factory):
        msg = message_factory()
        assert msg.sources is None
        assert msg.party_id is None
        assert msg.current_chat_title is None
        assert msg.quick_replies is None
        assert msg.rag_query is None

    def test_all_fields(self, message_factory):
        from src.models.chat import Role

        msg = message_factory(
            role=Role.ASSISTANT,
            content="Réponse complète.",
            sources=[{"url": "https://source.fr", "title": "Source 1"}],
            party_id="ps",
            current_chat_title="Titre de chat",
            quick_replies=["Question 1", "Question 2", "Question 3"],
            rag_query=["query1", "query2"],
        )
        assert msg.role == Role.ASSISTANT
        assert msg.content == "Réponse complète."
        assert msg.sources == [{"url": "https://source.fr", "title": "Source 1"}]
        assert msg.party_id == "ps"
        assert msg.current_chat_title == "Titre de chat"
        assert msg.quick_replies == ["Question 1", "Question 2", "Question 3"]
        assert msg.rag_query == ["query1", "query2"]

    def test_missing_required_raises(self):
        from src.models.chat import Message

        with pytest.raises(ValidationError):
            Message(content="no role")

    def test_model_dump(self, message_factory):
        msg = message_factory()
        d = msg.model_dump()
        assert d["role"] == "user"
        assert d["content"] == "Question de test"


class TestChatSession:
    def test_valid_construction(self, message_factory):
        from src.models.chat import ChatSession

        msgs = [message_factory()]
        session = ChatSession(
            user_id="uid-123",
            party_id="ps",
            chat_history=msgs,
        )
        assert session.user_id == "uid-123"
        assert session.party_id == "ps"
        assert len(session.chat_history) == 1

    def test_defaults(self, message_factory):
        from src.models.chat import ChatSession

        session = ChatSession(
            user_id="uid-123",
            party_id="rn",
            chat_history=[message_factory()],
        )
        assert session.title is None
        assert session.created_at is None

    def test_all_fields(self, message_factory):
        from src.models.chat import ChatSession

        now = datetime(2026, 3, 1)
        session = ChatSession(
            user_id="uid-456",
            party_id="lfi",
            chat_history=[message_factory()],
            title="Mon premier chat",
            created_at=now,
        )
        assert session.title == "Mon premier chat"
        assert session.created_at == now

    def test_missing_required_raises(self):
        from src.models.chat import ChatSession

        with pytest.raises(ValidationError):
            ChatSession(user_id="uid", chat_history=[])  # party_id missing

    def test_empty_chat_history(self):
        from src.models.chat import ChatSession

        session = ChatSession(user_id="u", party_id="p", chat_history=[])
        assert session.chat_history == []


class TestProConAssessment:
    def test_valid_construction(self, message_factory):
        from src.models.chat import ProConAssessment

        msgs = [message_factory()]
        assessment = ProConAssessment(
            user_id="uid-789",
            party_id="eelv",
            chat_history=msgs,
        )
        assert assessment.user_id == "uid-789"
        assert assessment.party_id == "eelv"
        assert len(assessment.chat_history) == 1

    def test_missing_required_raises(self):
        from src.models.chat import ProConAssessment

        with pytest.raises(ValidationError):
            ProConAssessment(user_id="u", chat_history=[])  # party_id missing


class TestGroupChatSession:
    def test_valid_required_fields(self, message_factory):
        from src.models.chat import GroupChatSession, LLMSize

        session = GroupChatSession(
            session_id="sess-001",
            chat_history=[message_factory()],
            chat_response_llm_size=LLMSize.LARGE,
        )
        assert session.session_id == "sess-001"
        assert session.chat_response_llm_size == LLMSize.LARGE

    def test_defaults(self, message_factory):
        from src.models.chat import GroupChatSession, LLMSize

        session = GroupChatSession(
            session_id="sess-002",
            chat_history=[message_factory()],
            chat_response_llm_size=LLMSize.SMALL,
        )
        assert session.title is None
        assert session.last_quick_replies == []
        assert session.is_cacheable is True
        assert session.scope == "national"
        assert session.municipality_code is None
        assert session.electoral_list_panel_numbers == []
        assert session.selected_electoral_lists == []
        assert session.locale == "fr"

    def test_all_fields(self, message_factory):
        from src.models.chat import GroupChatSession, LLMSize

        session = GroupChatSession(
            session_id="sess-003",
            chat_history=[message_factory()],
            chat_response_llm_size=LLMSize.LARGE,
            title="Chat titre",
            last_quick_replies=["q1", "q2"],
            is_cacheable=False,
            scope="local",
            municipality_code="75056",
            electoral_list_panel_numbers=[1, 2, 3],
            selected_electoral_lists=[{"panel_number": 1, "list_label": "Liste A"}],
            locale="en",
        )
        assert session.title == "Chat titre"
        assert session.last_quick_replies == ["q1", "q2"]
        assert session.is_cacheable is False
        assert session.scope == "local"
        assert session.municipality_code == "75056"
        assert session.electoral_list_panel_numbers == [1, 2, 3]
        assert session.locale == "en"

    def test_invalid_locale_raises(self, message_factory):
        from src.models.chat import GroupChatSession, LLMSize

        with pytest.raises(ValidationError):
            GroupChatSession(
                session_id="sess-bad",
                chat_history=[message_factory()],
                chat_response_llm_size=LLMSize.LARGE,
                locale="de",  # not in Literal["fr", "en"]
            )

    def test_missing_required_raises(self):
        from src.models.chat import GroupChatSession

        with pytest.raises(ValidationError):
            GroupChatSession(session_id="x", chat_history=[])  # llm_size missing


class TestCachedResponse:
    def test_valid_required_fields(self):
        from src.models.chat import CachedResponse

        now = datetime(2026, 3, 14)
        cr = CachedResponse(content="Cached answer.", created_at=now)
        assert cr.content == "Cached answer."
        assert cr.created_at == now

    def test_defaults(self):
        from src.models.chat import CachedResponse

        cr = CachedResponse(content="x", created_at=datetime(2026, 1, 1))
        assert cr.sources is None
        assert cr.rag_query is None
        assert cr.cached_conversation_history is None
        assert cr.depth is None
        assert cr.user_message_depth is None

    def test_all_fields(self):
        from src.models.chat import CachedResponse

        now = datetime(2026, 3, 14)
        cr = CachedResponse(
            content="Full cached response.",
            sources=[{"url": "https://source.fr"}],
            created_at=now,
            rag_query=["économie", "logement"],
            cached_conversation_history="User: bonjour\nAssistant: bonjour",
            depth=4,
            user_message_depth=2,
        )
        assert cr.sources == [{"url": "https://source.fr"}]
        assert cr.rag_query == ["économie", "logement"]
        assert cr.cached_conversation_history == "User: bonjour\nAssistant: bonjour"
        assert cr.depth == 4
        assert cr.user_message_depth == 2

    def test_missing_created_at_raises(self):
        from src.models.chat import CachedResponse

        with pytest.raises(ValidationError):
            CachedResponse(content="x")  # created_at required


# ---------------------------------------------------------------------------
# src/models/assistant.py
# ---------------------------------------------------------------------------


class TestAssistant:
    def test_valid_required_fields(self):
        from src.models.assistant import Assistant

        a = Assistant(
            assistant_id="my-assistant",
            name="MyBot",
            long_name="My Chat Bot",
            description="A helpful bot.",
            website_url="https://mybot.fr",
        )
        assert a.assistant_id == "my-assistant"
        assert a.name == "MyBot"
        assert a.long_name == "My Chat Bot"
        assert a.description == "A helpful bot."
        assert a.website_url == "https://mybot.fr"

    def test_defaults(self):
        from src.models.assistant import Assistant

        a = Assistant(
            assistant_id="x",
            name="X",
            long_name="X Long",
            description="desc",
            website_url="https://x.fr",
        )
        assert a.logo_url == ""
        assert a.background_color == "#4A90D9"

    def test_all_fields(self):
        from src.models.assistant import Assistant

        a = Assistant(
            assistant_id="cv",
            name="ChatVote",
            long_name="ChatVote Assistant",
            description="desc",
            website_url="https://chatvote.fr",
            logo_url="https://logo.svg",
            background_color="#1A2B3C",
        )
        assert a.logo_url == "https://logo.svg"
        assert a.background_color == "#1A2B3C"

    def test_party_id_property(self):
        from src.models.assistant import Assistant

        a = Assistant(
            assistant_id="cv-id",
            name="ChatVote",
            long_name="ChatVote Assistant",
            description="desc",
            website_url="https://chatvote.fr",
        )
        # party_id is an alias for assistant_id
        assert a.party_id == "cv-id"

    def test_missing_required_raises(self):
        from src.models.assistant import Assistant

        with pytest.raises(ValidationError):
            Assistant(name="X", long_name="X", description="d", website_url="u")

    def test_model_dump(self):
        from src.models.assistant import Assistant

        a = Assistant(
            assistant_id="cv",
            name="ChatVote",
            long_name="ChatVote Assistant",
            description="desc",
            website_url="https://chatvote.fr",
        )
        d = a.model_dump()
        assert d["assistant_id"] == "cv"
        assert d["name"] == "ChatVote"


class TestChatvoteAssistantConstant:
    def test_exists_and_type(self):
        from src.models.assistant import CHATVOTE_ASSISTANT, Assistant

        assert isinstance(CHATVOTE_ASSISTANT, Assistant)

    def test_values(self):
        from src.models.assistant import CHATVOTE_ASSISTANT, ASSISTANT_ID

        assert CHATVOTE_ASSISTANT.assistant_id == ASSISTANT_ID
        assert CHATVOTE_ASSISTANT.name == "ChatVote"
        assert CHATVOTE_ASSISTANT.website_url == "https://chatvote.fr"

    def test_party_id_matches_assistant_id(self):
        from src.models.assistant import CHATVOTE_ASSISTANT

        assert CHATVOTE_ASSISTANT.party_id == CHATVOTE_ASSISTANT.assistant_id


class TestAssistantIdConstant:
    def test_value(self):
        from src.models.assistant import ASSISTANT_ID

        assert ASSISTANT_ID == "chat-vote"

    def test_is_str(self):
        from src.models.assistant import ASSISTANT_ID

        assert isinstance(ASSISTANT_ID, str)


# ---------------------------------------------------------------------------
# src/models/vote.py
# ---------------------------------------------------------------------------


def _make_voting_results_overall(**overrides):
    from src.models.vote import VotingResultsOverall

    defaults = dict(yes=300, no=100, abstain=50, not_voted=20, members=470)
    return VotingResultsOverall(**(defaults | overrides))


def _make_voting_results_by_party(**overrides):
    from src.models.vote import VotingResultsByParty

    defaults = dict(party="ps", members=50, yes=40, no=5, abstain=3, not_voted=2)
    return VotingResultsByParty(**(defaults | overrides))


def _make_voting_results(**overrides):
    from src.models.vote import VotingResults

    defaults = dict(
        overall=_make_voting_results_overall(),
        by_party=[_make_voting_results_by_party()],
    )
    return VotingResults(**(defaults | overrides))


def _make_vote(**overrides):
    from src.models.vote import Vote, Link

    defaults = dict(
        id="vote-001",
        url="https://votes.fr/001",
        date="2025-06-15",
        title="Budget municipal 2025",
        subtitle=None,
        detail_text=None,
        links=[Link(url="https://votes.fr/doc", title="Document")],
        voting_results=_make_voting_results(),
        short_description="Budget",
        vote_category="finance",
        submitting_parties=["ps"],
    )
    return Vote(**(defaults | overrides))


class TestLink:
    def test_valid(self):
        from src.models.vote import Link

        link = Link(url="https://example.fr", title="Lien")
        assert link.url == "https://example.fr"
        assert link.title == "Lien"

    def test_missing_field_raises(self):
        from src.models.vote import Link

        with pytest.raises(ValidationError):
            Link(url="https://example.fr")  # title missing

    def test_model_dump(self):
        from src.models.vote import Link

        d = Link(url="https://x.fr", title="X").model_dump()
        assert d["url"] == "https://x.fr"
        assert d["title"] == "X"


class TestVotingResultsOverall:
    def test_valid(self):
        vro = _make_voting_results_overall()
        assert vro.yes == 300
        assert vro.no == 100
        assert vro.abstain == 50
        assert vro.not_voted == 20
        assert vro.members == 470

    def test_missing_field_raises(self):
        from src.models.vote import VotingResultsOverall

        with pytest.raises(ValidationError):
            VotingResultsOverall(yes=1, no=0, abstain=0, not_voted=0)  # members missing

    def test_model_dump(self):
        d = _make_voting_results_overall().model_dump()
        assert d["yes"] == 300
        assert d["members"] == 470


class TestVotingResultsByParty:
    def test_valid_required_fields(self):
        vrbp = _make_voting_results_by_party()
        assert vrbp.party == "ps"
        assert vrbp.members == 50
        assert vrbp.yes == 40
        assert vrbp.no == 5
        assert vrbp.abstain == 3
        assert vrbp.not_voted == 2

    def test_default_justification(self):
        vrbp = _make_voting_results_by_party()
        assert vrbp.justification is None

    def test_with_justification(self):
        vrbp = _make_voting_results_by_party(
            justification="Le PS a voté pour le budget."
        )
        assert vrbp.justification == "Le PS a voté pour le budget."

    def test_missing_field_raises(self):
        from src.models.vote import VotingResultsByParty

        with pytest.raises(ValidationError):
            VotingResultsByParty(party="ps", members=50, yes=40, no=5, abstain=3)

    def test_model_dump(self):
        d = _make_voting_results_by_party().model_dump()
        assert d["party"] == "ps"
        assert d["justification"] is None


class TestVotingResults:
    def test_valid(self):
        vr = _make_voting_results()
        assert vr.overall.yes == 300
        assert len(vr.by_party) == 1

    def test_multiple_parties(self):
        from src.models.vote import VotingResults

        vr = VotingResults(
            overall=_make_voting_results_overall(),
            by_party=[
                _make_voting_results_by_party(party="ps"),
                _make_voting_results_by_party(party="rn"),
            ],
        )
        assert len(vr.by_party) == 2

    def test_missing_field_raises(self):
        from src.models.vote import VotingResults

        with pytest.raises(ValidationError):
            VotingResults(overall=_make_voting_results_overall())  # by_party missing


class TestVote:
    def test_valid_required_fields(self):
        vote = _make_vote()
        assert vote.id == "vote-001"
        assert vote.url == "https://votes.fr/001"
        assert vote.date == "2025-06-15"
        assert vote.title == "Budget municipal 2025"

    def test_optional_fields_can_be_none(self):
        vote = _make_vote(subtitle=None, detail_text=None, short_description=None)
        assert vote.subtitle is None
        assert vote.detail_text is None
        assert vote.short_description is None

    def test_optional_fields_set(self):
        vote = _make_vote(
            subtitle="Sous-titre",
            detail_text="Détail long.",
            short_description="Court",
            vote_category="social",
            submitting_parties=["eelv", "ps"],
        )
        assert vote.subtitle == "Sous-titre"
        assert vote.detail_text == "Détail long."
        assert vote.short_description == "Court"
        assert vote.vote_category == "social"
        assert vote.submitting_parties == ["eelv", "ps"]

    def test_links_list(self):
        from src.models.vote import Link

        vote = _make_vote(
            links=[
                Link(url="https://a.fr", title="A"),
                Link(url="https://b.fr", title="B"),
            ]
        )
        assert len(vote.links) == 2

    def test_missing_required_raises(self):
        from src.models.vote import Vote

        with pytest.raises(ValidationError):
            Vote(
                id="x",
                url="https://x.fr",
                date="2025-01-01",
                # title missing
                subtitle=None,
                detail_text=None,
                links=[],
                voting_results=_make_voting_results(),
                short_description=None,
                vote_category=None,
                submitting_parties=None,
            )

    def test_model_dump(self):
        d = _make_vote().model_dump()
        assert d["id"] == "vote-001"
        assert d["title"] == "Budget municipal 2025"


# ---------------------------------------------------------------------------
# src/models/dtos.py
# ---------------------------------------------------------------------------


class TestCreateSessionRequest:
    def test_valid(self):
        from src.models.dtos import CreateSessionRequest

        req = CreateSessionRequest(party_id="ps", user_id="uid-001")
        assert req.party_id == "ps"
        assert req.user_id == "uid-001"

    def test_missing_raises(self):
        from src.models.dtos import CreateSessionRequest

        with pytest.raises(ValidationError):
            CreateSessionRequest(party_id="ps")  # user_id missing


class TestChatAnswerRequest:
    def test_valid(self):
        from src.models.dtos import ChatAnswerRequest

        req = ChatAnswerRequest(
            user_id="uid-001",
            chat_session_id="sess-001",
            user_message="Qu'est-ce que vous proposez?",
        )
        assert req.user_id == "uid-001"
        assert req.chat_session_id == "sess-001"

    def test_missing_raises(self):
        from src.models.dtos import ChatAnswerRequest

        with pytest.raises(ValidationError):
            ChatAnswerRequest(user_id="uid-001", user_message="msg")


class TestGroupChatDto:
    def test_valid(self, message_factory, party_factory):
        from src.models.dtos import GroupChatDto

        dto = GroupChatDto(
            chat_history=[message_factory()],
            pre_selected_parties=[party_factory()],
        )
        assert len(dto.chat_history) == 1
        assert len(dto.pre_selected_parties) == 1

    def test_empty_lists(self):
        from src.models.dtos import GroupChatDto

        dto = GroupChatDto(chat_history=[], pre_selected_parties=[])
        assert dto.chat_history == []
        assert dto.pre_selected_parties == []


class TestGroupChatResponseDto:
    def test_valid(self, message_factory):
        from src.models.dtos import GroupChatResponseDto

        dto = GroupChatResponseDto(
            new_messages=[message_factory()],
            current_chat_title="Mon chat",
            quick_replies=["q1", "q2"],
        )
        assert dto.current_chat_title == "Mon chat"
        assert dto.quick_replies == ["q1", "q2"]


class TestStatusIndicator:
    def test_values(self):
        from src.models.dtos import StatusIndicator

        assert StatusIndicator.ERROR == "error"
        assert StatusIndicator.SUCCESS == "success"

    def test_is_str_enum(self):
        from src.models.dtos import StatusIndicator

        assert isinstance(StatusIndicator.ERROR, str)


class TestChatScope:
    def test_values(self):
        from src.models.dtos import ChatScope

        assert ChatScope.NATIONAL == "national"
        assert ChatScope.LOCAL == "local"

    def test_all_members(self):
        from src.models.dtos import ChatScope

        members = {m.value for m in ChatScope}
        assert members == {"national", "local"}


class TestStatus:
    def test_valid(self):
        from src.models.dtos import Status, StatusIndicator

        s = Status(indicator=StatusIndicator.SUCCESS, message="OK")
        assert s.indicator == StatusIndicator.SUCCESS
        assert s.message == "OK"

    def test_error_status(self):
        from src.models.dtos import Status, StatusIndicator

        s = Status(indicator=StatusIndicator.ERROR, message="Something went wrong")
        assert s.indicator == StatusIndicator.ERROR

    def test_missing_raises(self):
        from src.models.dtos import Status, StatusIndicator

        with pytest.raises(ValidationError):
            Status(indicator=StatusIndicator.SUCCESS)  # message missing


class TestInitChatSessionDto:
    def test_valid_required_fields(self, message_factory):
        from src.models.dtos import InitChatSessionDto

        dto = InitChatSessionDto(
            session_id="sess-001",
            chat_history=[message_factory()],
            current_title="Titre",
        )
        assert dto.session_id == "sess-001"
        assert dto.current_title == "Titre"

    def test_defaults(self, message_factory):
        from src.models.dtos import InitChatSessionDto, ChatScope
        from src.models.general import LLMSize

        dto = InitChatSessionDto(
            session_id="sess-001",
            chat_history=[message_factory()],
            current_title="Titre",
        )
        assert dto.chat_response_llm_size == LLMSize.LARGE
        assert dto.last_quick_replies == []
        assert dto.is_cacheable is True
        assert dto.scope == ChatScope.NATIONAL
        assert dto.municipality_code is None
        assert dto.electoral_list_panel_numbers == []
        assert dto.selected_electoral_lists == []
        assert dto.locale == "fr"

    def test_all_fields(self, message_factory):
        from src.models.dtos import InitChatSessionDto, ChatScope
        from src.models.general import LLMSize

        dto = InitChatSessionDto(
            session_id="sess-002",
            chat_history=[message_factory()],
            current_title="Titre local",
            chat_response_llm_size=LLMSize.SMALL,
            last_quick_replies=["q1"],
            is_cacheable=False,
            scope=ChatScope.LOCAL,
            municipality_code="75056",
            electoral_list_panel_numbers=[1],
            selected_electoral_lists=[{"panel_number": 1}],
            locale="en",
        )
        assert dto.scope == ChatScope.LOCAL
        assert dto.municipality_code == "75056"
        assert dto.locale == "en"

    def test_invalid_locale_raises(self, message_factory):
        from src.models.dtos import InitChatSessionDto

        with pytest.raises(ValidationError):
            InitChatSessionDto(
                session_id="sess-003",
                chat_history=[message_factory()],
                current_title="Titre",
                locale="es",
            )


class TestChatSessionInitializedDto:
    def test_valid_with_session_id(self):
        from src.models.dtos import ChatSessionInitializedDto, Status, StatusIndicator

        dto = ChatSessionInitializedDto(
            session_id="sess-001",
            status=Status(indicator=StatusIndicator.SUCCESS, message="OK"),
        )
        assert dto.session_id == "sess-001"

    def test_valid_with_none_session_id(self):
        from src.models.dtos import ChatSessionInitializedDto, Status, StatusIndicator

        dto = ChatSessionInitializedDto(
            session_id=None,
            status=Status(indicator=StatusIndicator.ERROR, message="Error"),
        )
        assert dto.session_id is None


class TestProConPerspectiveRequestDto:
    def test_valid(self):
        from src.models.dtos import ProConPerspectiveRequestDto

        dto = ProConPerspectiveRequestDto(
            request_id="req-001",
            party_id="ps",
            last_user_message="Question?",
            last_assistant_message="Réponse.",
        )
        assert dto.request_id == "req-001"
        assert dto.party_id == "ps"

    def test_missing_raises(self):
        from src.models.dtos import ProConPerspectiveRequestDto

        with pytest.raises(ValidationError):
            ProConPerspectiveRequestDto(request_id="req-001", party_id="ps")


class TestProConPerspectiveDto:
    def test_valid_with_none_request_id(self):
        from src.models.dtos import ProConPerspectiveDto, Status, StatusIndicator

        dto = ProConPerspectiveDto(
            request_id=None,
            status=Status(indicator=StatusIndicator.ERROR, message="Error"),
        )
        assert dto.request_id is None
        assert dto.message is None

    def test_valid_with_message(self, message_factory):
        from src.models.dtos import ProConPerspectiveDto, Status, StatusIndicator

        dto = ProConPerspectiveDto(
            request_id="req-001",
            message=message_factory(),
            status=Status(indicator=StatusIndicator.SUCCESS, message="OK"),
        )
        assert dto.request_id == "req-001"
        assert dto.message is not None


class TestCandidateProConPerspectiveRequestDto:
    def test_valid(self):
        from src.models.dtos import CandidateProConPerspectiveRequestDto

        dto = CandidateProConPerspectiveRequestDto(
            request_id="req-002",
            candidate_id="cand-001",
            last_user_message="Question?",
            last_assistant_message="Réponse.",
        )
        assert dto.candidate_id == "cand-001"

    def test_missing_raises(self):
        from src.models.dtos import CandidateProConPerspectiveRequestDto

        with pytest.raises(ValidationError):
            CandidateProConPerspectiveRequestDto(request_id="req-002")


class TestCandidateProConPerspectiveDto:
    def test_valid(self):
        from src.models.dtos import (
            CandidateProConPerspectiveDto,
            Status,
            StatusIndicator,
        )

        dto = CandidateProConPerspectiveDto(
            request_id="req-002",
            status=Status(indicator=StatusIndicator.SUCCESS, message="OK"),
        )
        assert dto.request_id == "req-002"
        assert dto.candidate_id is None
        assert dto.message is None

    def test_all_fields(self, message_factory):
        from src.models.dtos import (
            CandidateProConPerspectiveDto,
            Status,
            StatusIndicator,
        )

        dto = CandidateProConPerspectiveDto(
            request_id="req-003",
            candidate_id="cand-001",
            message=message_factory(),
            status=Status(indicator=StatusIndicator.SUCCESS, message="OK"),
        )
        assert dto.candidate_id == "cand-001"
        assert dto.message is not None


class TestVotingBehaviorRequestDto:
    def test_valid_required(self):
        from src.models.dtos import VotingBehaviorRequestDto

        dto = VotingBehaviorRequestDto(
            request_id="req-003",
            party_id="rn",
            last_user_message="Comment a voté le RN?",
            last_assistant_message="Le RN a voté contre.",
        )
        assert dto.request_id == "req-003"
        assert dto.party_id == "rn"

    def test_defaults(self):
        from src.models.dtos import VotingBehaviorRequestDto
        from src.models.general import LLMSize

        dto = VotingBehaviorRequestDto(
            request_id="req-004",
            party_id="ps",
            last_user_message="msg",
            last_assistant_message="resp",
        )
        assert dto.summary_llm_size == LLMSize.LARGE
        assert dto.user_is_logged_in is False

    def test_all_fields(self):
        from src.models.dtos import VotingBehaviorRequestDto
        from src.models.general import LLMSize

        dto = VotingBehaviorRequestDto(
            request_id="req-005",
            party_id="ps",
            last_user_message="msg",
            last_assistant_message="resp",
            summary_llm_size=LLMSize.SMALL,
            user_is_logged_in=True,
        )
        assert dto.summary_llm_size == LLMSize.SMALL
        assert dto.user_is_logged_in is True


class TestParliamentaryQuestionRequestDto:
    def test_valid(self):
        from src.models.dtos import ParliamentaryQuestionRequestDto

        dto = ParliamentaryQuestionRequestDto(
            request_id="req-006",
            party_id="eelv",
            last_user_message="Questions?",
            last_assistant_message="Réponses.",
        )
        assert dto.request_id == "req-006"
        assert dto.party_id == "eelv"


class TestVotingBehaviorVoteDto:
    def test_valid(self):
        from src.models.dtos import VotingBehaviorVoteDto

        dto = VotingBehaviorVoteDto(request_id="req-007", vote=_make_vote())
        assert dto.request_id == "req-007"
        assert dto.vote.id == "vote-001"


class TestVotingBehaviorSummaryChunkDto:
    def test_valid(self):
        from src.models.dtos import VotingBehaviorSummaryChunkDto

        dto = VotingBehaviorSummaryChunkDto(
            request_id="req-008",
            chunk_index=0,
            summary_chunk="Premier chunk.",
            is_end=False,
        )
        assert dto.chunk_index == 0
        assert dto.is_end is False

    def test_last_chunk(self):
        from src.models.dtos import VotingBehaviorSummaryChunkDto

        dto = VotingBehaviorSummaryChunkDto(
            request_id="req-009",
            chunk_index=5,
            summary_chunk="Fin.",
            is_end=True,
        )
        assert dto.is_end is True

    def test_missing_raises(self):
        from src.models.dtos import VotingBehaviorSummaryChunkDto

        with pytest.raises(ValidationError):
            VotingBehaviorSummaryChunkDto(
                request_id="req-010",
                chunk_index=0,
                is_end=False,
            )


class TestVotingBehaviorDto:
    def test_valid(self):
        from src.models.dtos import VotingBehaviorDto, Status, StatusIndicator

        dto = VotingBehaviorDto(
            request_id="req-011",
            message="Résumé du comportement.",
            status=Status(indicator=StatusIndicator.SUCCESS, message="OK"),
            votes=[_make_vote()],
            rag_query="Comment vote le RN?",
        )
        assert dto.request_id == "req-011"
        assert len(dto.votes) == 1
        assert dto.rag_query == "Comment vote le RN?"

    def test_optional_none_values(self):
        from src.models.dtos import VotingBehaviorDto, Status, StatusIndicator

        dto = VotingBehaviorDto(
            request_id=None,
            message="Résumé.",
            status=Status(indicator=StatusIndicator.ERROR, message="Err"),
            votes=[],
            rag_query=None,
        )
        assert dto.request_id is None
        assert dto.rag_query is None


class TestParliamentaryQuestionDto:
    def test_valid(self):
        from src.models.dtos import ParliamentaryQuestionDto, Status, StatusIndicator

        dto = ParliamentaryQuestionDto(
            request_id="req-012",
            status=Status(indicator=StatusIndicator.SUCCESS, message="OK"),
            parliamentary_questions=[_make_vote()],
            rag_query="Questions parlementaires",
        )
        assert dto.request_id == "req-012"
        assert len(dto.parliamentary_questions) == 1

    def test_none_values(self):
        from src.models.dtos import ParliamentaryQuestionDto, Status, StatusIndicator

        dto = ParliamentaryQuestionDto(
            request_id=None,
            status=Status(indicator=StatusIndicator.ERROR, message="Err"),
            parliamentary_questions=[],
            rag_query=None,
        )
        assert dto.request_id is None
        assert dto.rag_query is None


class TestChatUserMessageDto:
    def test_valid(self):
        from src.models.dtos import ChatUserMessageDto

        dto = ChatUserMessageDto(
            session_id="sess-abc",
            user_message="Qu'est-ce que vous proposez?",
            party_ids=["ps", "rn"],
        )
        assert dto.session_id == "sess-abc"
        assert dto.user_message == "Qu'est-ce que vous proposez?"
        assert dto.party_ids == ["ps", "rn"]

    def test_defaults(self):
        from src.models.dtos import ChatUserMessageDto, ChatScope

        dto = ChatUserMessageDto(
            session_id="sess-def",
            user_message="Message",
            party_ids=["ps"],
        )
        assert dto.user_is_logged_in is False
        assert dto.scope == ChatScope.NATIONAL
        assert dto.municipality_code is None
        assert dto.locale == "fr"

    def test_all_fields(self):
        from src.models.dtos import ChatUserMessageDto, ChatScope

        dto = ChatUserMessageDto(
            session_id="sess-ghi",
            user_message="Message local",
            party_ids=["ps"],
            user_is_logged_in=True,
            scope=ChatScope.LOCAL,
            municipality_code="75056",
            locale="en",
        )
        assert dto.user_is_logged_in is True
        assert dto.scope == ChatScope.LOCAL
        assert dto.municipality_code == "75056"
        assert dto.locale == "en"

    def test_session_id_empty_raises(self):
        from src.models.dtos import ChatUserMessageDto

        with pytest.raises(ValidationError):
            ChatUserMessageDto(
                session_id="",
                user_message="Message",
                party_ids=["ps"],
            )

    def test_session_id_whitespace_only_raises(self):
        from src.models.dtos import ChatUserMessageDto

        with pytest.raises(ValidationError):
            ChatUserMessageDto(
                session_id="   ",
                user_message="Message",
                party_ids=["ps"],
            )

    def test_session_id_valid_non_empty(self):
        from src.models.dtos import ChatUserMessageDto

        dto = ChatUserMessageDto(
            session_id="valid-session",
            user_message="Message",
            party_ids=["ps"],
        )
        assert dto.session_id == "valid-session"

    def test_user_message_max_length(self):
        from src.models.dtos import ChatUserMessageDto

        long_msg = "a" * 501
        with pytest.raises(ValidationError):
            ChatUserMessageDto(
                session_id="sess-x",
                user_message=long_msg,
                party_ids=["ps"],
            )

    def test_user_message_exactly_500_chars(self):
        from src.models.dtos import ChatUserMessageDto

        msg = "a" * 500
        dto = ChatUserMessageDto(
            session_id="sess-x", user_message=msg, party_ids=["ps"]
        )
        assert len(dto.user_message) == 500


class TestTitleDto:
    def test_valid(self):
        from src.models.dtos import TitleDto

        dto = TitleDto(session_id="sess-001", title="Nouveau titre")
        assert dto.session_id == "sess-001"
        assert dto.title == "Nouveau titre"

    def test_missing_raises(self):
        from src.models.dtos import TitleDto

        with pytest.raises(ValidationError):
            TitleDto(session_id="sess-001")


class TestSourcesDto:
    def test_valid(self):
        from src.models.dtos import SourcesDto

        dto = SourcesDto(
            session_id="sess-001",
            sources=[{"url": "https://source.fr", "title": "Source"}],
            party_id="ps",
            rag_query=["économie"],
        )
        assert dto.session_id == "sess-001"
        assert len(dto.sources) == 1

    def test_optional_none_values(self):
        from src.models.dtos import SourcesDto

        dto = SourcesDto(
            session_id="sess-002",
            sources=[],
            party_id="test-party",
            rag_query=None,
        )
        assert dto.party_id == "test-party"
        assert dto.rag_query is None


class TestRespondingPartiesDto:
    def test_valid(self):
        from src.models.dtos import RespondingPartiesDto

        dto = RespondingPartiesDto(session_id="sess-001", party_ids=["ps", "rn"])
        assert dto.party_ids == ["ps", "rn"]

    def test_empty_party_ids(self):
        from src.models.dtos import RespondingPartiesDto

        dto = RespondingPartiesDto(session_id="sess-001", party_ids=[])
        assert dto.party_ids == []


class TestPartyResponseChunkDto:
    def test_valid(self):
        from src.models.dtos import PartyResponseChunkDto

        dto = PartyResponseChunkDto(
            session_id="sess-001",
            party_id="ps",
            chunk_index=0,
            chunk_content="Premier chunk de réponse.",
            is_end=False,
        )
        assert dto.chunk_index == 0
        assert dto.is_end is False

    def test_none_party_id(self):
        from src.models.dtos import PartyResponseChunkDto

        dto = PartyResponseChunkDto(
            session_id="sess-001",
            party_id=None,
            chunk_index=1,
            chunk_content="Fin.",
            is_end=True,
        )
        assert dto.party_id is None
        assert dto.is_end is True


class TestStreamResetDto:
    def test_valid(self):
        from src.models.dtos import StreamResetDto

        dto = StreamResetDto(
            session_id="sess-001",
            party_id="ps",
            reason="Rate limit on google-gemini-2.5-flash",
        )
        assert dto.session_id == "sess-001"
        assert dto.party_id == "ps"
        assert "Rate limit" in dto.reason

    def test_none_party_id(self):
        from src.models.dtos import StreamResetDto

        dto = StreamResetDto(
            session_id="sess-002",
            party_id=None,
            reason="Model unavailable",
        )
        assert dto.party_id is None

    def test_missing_raises(self):
        from src.models.dtos import StreamResetDto

        with pytest.raises(ValidationError):
            StreamResetDto(session_id="sess-003", party_id="ps")  # reason missing


class TestPartyResponseCompleteDto:
    def test_valid(self):
        from src.models.dtos import PartyResponseCompleteDto, Status, StatusIndicator

        dto = PartyResponseCompleteDto(
            session_id="sess-001",
            party_id="ps",
            complete_message="Réponse complète.",
            status=Status(indicator=StatusIndicator.SUCCESS, message="OK"),
        )
        assert dto.complete_message == "Réponse complète."

    def test_none_party_id(self):
        from src.models.dtos import PartyResponseCompleteDto, Status, StatusIndicator

        dto = PartyResponseCompleteDto(
            session_id="sess-002",
            party_id=None,
            complete_message="Msg.",
            status=Status(indicator=StatusIndicator.SUCCESS, message="OK"),
        )
        assert dto.party_id is None


class TestChatResponseCompleteDto:
    def test_valid(self):
        from src.models.dtos import ChatResponseCompleteDto, Status, StatusIndicator

        dto = ChatResponseCompleteDto(
            session_id="sess-001",
            status=Status(indicator=StatusIndicator.SUCCESS, message="Done"),
        )
        assert dto.session_id == "sess-001"

    def test_none_session_id(self):
        from src.models.dtos import ChatResponseCompleteDto, Status, StatusIndicator

        dto = ChatResponseCompleteDto(
            session_id=None,
            status=Status(indicator=StatusIndicator.ERROR, message="Error"),
        )
        assert dto.session_id is None


class TestQuickRepliesAndTitleDto:
    def test_valid(self):
        from src.models.dtos import QuickRepliesAndTitleDto

        dto = QuickRepliesAndTitleDto(
            session_id="sess-001",
            quick_replies=["q1", "q2", "q3"],
            title="Titre du chat",
        )
        assert dto.quick_replies == ["q1", "q2", "q3"]
        assert dto.title == "Titre du chat"

    def test_empty_quick_replies(self):
        from src.models.dtos import QuickRepliesAndTitleDto

        dto = QuickRepliesAndTitleDto(
            session_id="sess-001", quick_replies=[], title="T"
        )
        assert dto.quick_replies == []


class TestRequestSummaryDto:
    def test_valid(self, message_factory):
        from src.models.dtos import RequestSummaryDto

        dto = RequestSummaryDto(chat_history=[message_factory()])
        assert len(dto.chat_history) == 1

    def test_empty_history(self):
        from src.models.dtos import RequestSummaryDto

        dto = RequestSummaryDto(chat_history=[])
        assert dto.chat_history == []


class TestSummaryDto:
    def test_valid(self):
        from src.models.dtos import SummaryDto, Status, StatusIndicator

        dto = SummaryDto(
            chat_summary="Résumé du chat.",
            status=Status(indicator=StatusIndicator.SUCCESS, message="OK"),
        )
        assert dto.chat_summary == "Résumé du chat."

    def test_error_status(self):
        from src.models.dtos import SummaryDto, Status, StatusIndicator

        dto = SummaryDto(
            chat_summary="",
            status=Status(indicator=StatusIndicator.ERROR, message="Error"),
        )
        assert dto.status.indicator == StatusIndicator.ERROR


# ---------------------------------------------------------------------------
# src/models/structured_outputs.py
# ---------------------------------------------------------------------------


class TestRAG:
    def test_valid(self):
        from src.models.structured_outputs import RAG

        rag = RAG(
            chat_answer="**L'économie** est au cœur de nos propositions.",
            chat_title="Économie et emploi",
        )
        assert rag.chat_answer.startswith("**L'économie**")
        assert rag.chat_title == "Économie et emploi"

    def test_missing_raises(self):
        from src.models.structured_outputs import RAG

        with pytest.raises(ValidationError):
            RAG(chat_answer="answer")  # chat_title missing

    def test_model_dump(self):
        from src.models.structured_outputs import RAG

        d = RAG(chat_answer="ans", chat_title="title").model_dump()
        assert "chat_answer" in d
        assert "chat_title" in d


class TestQuickReplyGenerator:
    def test_valid(self):
        from src.models.structured_outputs import QuickReplyGenerator

        qrg = QuickReplyGenerator(quick_replies=["q1", "q2", "q3"])
        assert len(qrg.quick_replies) == 3

    def test_empty_list(self):
        from src.models.structured_outputs import QuickReplyGenerator

        qrg = QuickReplyGenerator(quick_replies=[])
        assert qrg.quick_replies == []

    def test_model_dump(self):
        from src.models.structured_outputs import QuickReplyGenerator

        d = QuickReplyGenerator(quick_replies=["a", "b"]).model_dump()
        assert d["quick_replies"] == ["a", "b"]


class TestPartyListGenerator:
    def test_valid(self):
        from src.models.structured_outputs import PartyListGenerator

        plg = PartyListGenerator(party_id_list=["ps", "rn", "lfi"])
        assert plg.party_id_list == ["ps", "rn", "lfi"]

    def test_chat_vote_in_list(self):
        from src.models.structured_outputs import PartyListGenerator

        plg = PartyListGenerator(party_id_list=["chat-vote"])
        assert "chat-vote" in plg.party_id_list

    def test_empty_list(self):
        from src.models.structured_outputs import PartyListGenerator

        plg = PartyListGenerator(party_id_list=[])
        assert plg.party_id_list == []


class TestQuestionTypeClassifier:
    def test_valid(self):
        from src.models.structured_outputs import QuestionTypeClassifier

        qtc = QuestionTypeClassifier(
            non_party_specific_question="Quelle est votre position sur l'économie?",
            is_comparing_question=False,
        )
        assert qtc.is_comparing_question is False

    def test_comparing_question(self):
        from src.models.structured_outputs import QuestionTypeClassifier

        qtc = QuestionTypeClassifier(
            non_party_specific_question="Comparez LFI et PS sur l'économie.",
            is_comparing_question=True,
        )
        assert qtc.is_comparing_question is True

    def test_missing_raises(self):
        from src.models.structured_outputs import QuestionTypeClassifier

        with pytest.raises(ValidationError):
            QuestionTypeClassifier(non_party_specific_question="x")


class TestChatSummaryGenerator:
    def test_valid(self):
        from src.models.structured_outputs import ChatSummaryGenerator

        csg = ChatSummaryGenerator(
            chat_summary="Le chat a porté sur l'économie et le logement."
        )
        assert "économie" in csg.chat_summary

    def test_model_dump(self):
        from src.models.structured_outputs import ChatSummaryGenerator

        d = ChatSummaryGenerator(chat_summary="résumé").model_dump()
        assert d["chat_summary"] == "résumé"


class TestGroupChatTitleQuickReplyGenerator:
    def test_valid(self):
        from src.models.structured_outputs import GroupChatTitleQuickReplyGenerator

        gen = GroupChatTitleQuickReplyGenerator(
            chat_title="Logement et loyer",
            quick_replies=["q1", "q2", "q3"],
        )
        assert gen.chat_title == "Logement et loyer"
        assert len(gen.quick_replies) == 3

    def test_missing_raises(self):
        from src.models.structured_outputs import GroupChatTitleQuickReplyGenerator

        with pytest.raises(ValidationError):
            GroupChatTitleQuickReplyGenerator(chat_title="x")  # quick_replies missing


class TestRerankingOutput:
    def test_valid(self):
        from src.models.structured_outputs import RerankingOutput

        ro = RerankingOutput(reranked_doc_indices=[2, 0, 1, 4, 3])
        assert ro.reranked_doc_indices == [2, 0, 1, 4, 3]

    def test_empty_list(self):
        from src.models.structured_outputs import RerankingOutput

        ro = RerankingOutput(reranked_doc_indices=[])
        assert ro.reranked_doc_indices == []

    def test_model_dump(self):
        from src.models.structured_outputs import RerankingOutput

        d = RerankingOutput(reranked_doc_indices=[0, 1]).model_dump()
        assert d["reranked_doc_indices"] == [0, 1]


class TestEntityDetector:
    def test_valid_all_fields(self):
        from src.models.structured_outputs import EntityDetector

        ed = EntityDetector(
            party_ids=["ps", "lfi"],
            candidate_ids=["cand-001"],
            needs_clarification=False,
            clarification_message="",
            reformulated_question="Quelle est la position du PS?",
        )
        assert ed.party_ids == ["ps", "lfi"]
        assert ed.candidate_ids == ["cand-001"]
        assert ed.needs_clarification is False
        assert ed.clarification_message == ""

    def test_needs_clarification_true(self):
        from src.models.structured_outputs import EntityDetector

        ed = EntityDetector(
            party_ids=[],
            candidate_ids=[],
            needs_clarification=True,
            clarification_message="Quel parti souhaitez-vous interroger?",
            reformulated_question="Question générale.",
        )
        assert ed.needs_clarification is True
        assert ed.clarification_message != ""

    def test_missing_raises(self):
        from src.models.structured_outputs import EntityDetector

        with pytest.raises(ValidationError):
            EntityDetector(
                party_ids=[],
                candidate_ids=[],
                needs_clarification=False,
                # clarification_message and reformulated_question missing
            )

    def test_model_dump(self):
        from src.models.structured_outputs import EntityDetector

        d = EntityDetector(
            party_ids=["ps"],
            candidate_ids=[],
            needs_clarification=False,
            clarification_message="",
            reformulated_question="Question.",
        ).model_dump()
        assert d["party_ids"] == ["ps"]


class TestChunkThemeClassification:
    def test_defaults(self):
        from src.models.structured_outputs import ChunkThemeClassification

        ctc = ChunkThemeClassification()
        assert ctc.theme is None
        assert ctc.sub_theme is None

    def test_with_values(self):
        from src.models.structured_outputs import ChunkThemeClassification

        ctc = ChunkThemeClassification(theme="economie", sub_theme="pouvoir d'achat")
        assert ctc.theme == "economie"
        assert ctc.sub_theme == "pouvoir d'achat"

    def test_model_dump(self):
        from src.models.structured_outputs import ChunkThemeClassification

        d = ChunkThemeClassification(theme="education").model_dump()
        assert d["theme"] == "education"
        assert d["sub_theme"] is None


# ---------------------------------------------------------------------------
# src/models/chunk_metadata.py
# ---------------------------------------------------------------------------


class TestFiabilite:
    def test_values(self):
        from src.models.chunk_metadata import Fiabilite

        assert Fiabilite.GOVERNMENT == 1
        assert Fiabilite.OFFICIAL == 2
        assert Fiabilite.PRESS == 3
        assert Fiabilite.SOCIAL_MEDIA == 4

    def test_is_int_enum(self):
        from src.models.chunk_metadata import Fiabilite

        assert isinstance(Fiabilite.GOVERNMENT, int)

    def test_ordering(self):
        from src.models.chunk_metadata import Fiabilite

        assert (
            Fiabilite.GOVERNMENT
            < Fiabilite.OFFICIAL
            < Fiabilite.PRESS
            < Fiabilite.SOCIAL_MEDIA
        )


class TestInferFiabilite:
    def test_exact_match_government(self):
        from src.models.chunk_metadata import _infer_fiabilite, Fiabilite

        assert _infer_fiabilite("justified_voting_behavior") == Fiabilite.GOVERNMENT
        assert _infer_fiabilite("parliamentary_question") == Fiabilite.GOVERNMENT
        assert _infer_fiabilite("profession_de_foi") == Fiabilite.GOVERNMENT

    def test_exact_match_official(self):
        from src.models.chunk_metadata import _infer_fiabilite, Fiabilite

        assert _infer_fiabilite("election_manifesto") == Fiabilite.OFFICIAL
        assert _infer_fiabilite("party_website") == Fiabilite.OFFICIAL

    def test_prefix_match(self):
        from src.models.chunk_metadata import _infer_fiabilite, Fiabilite

        assert _infer_fiabilite("candidate_website_blog") == Fiabilite.PRESS
        assert _infer_fiabilite("candidate_website_about") == Fiabilite.OFFICIAL
        assert _infer_fiabilite("candidate_website_programme") == Fiabilite.OFFICIAL

    def test_unknown_defaults_to_press(self):
        from src.models.chunk_metadata import _infer_fiabilite, Fiabilite

        assert _infer_fiabilite("some_unknown_source") == Fiabilite.PRESS
        assert _infer_fiabilite("") == Fiabilite.PRESS


class TestThemeTaxonomy:
    def test_is_list(self):
        from src.models.chunk_metadata import THEME_TAXONOMY

        assert isinstance(THEME_TAXONOMY, list)

    def test_contains_expected_themes(self):
        from src.models.chunk_metadata import THEME_TAXONOMY

        expected = {
            "economie",
            "education",
            "environnement",
            "sante",
            "securite",
            "immigration",
            "culture",
            "logement",
            "transport",
            "numerique",
            "agriculture",
            "justice",
            "international",
            "institutions",
        }
        assert set(THEME_TAXONOMY) == expected

    def test_count(self):
        from src.models.chunk_metadata import THEME_TAXONOMY

        assert len(THEME_TAXONOMY) == 14


class TestChunkMetadata:
    def test_valid_required_fields(self):
        from src.models.chunk_metadata import ChunkMetadata

        cm = ChunkMetadata(
            namespace="party-ps",
            source_document="election_manifesto",
        )
        assert cm.namespace == "party-ps"
        assert cm.source_document == "election_manifesto"

    def test_auto_fiabilite_from_source_document(self):
        from src.models.chunk_metadata import ChunkMetadata, Fiabilite

        cm = ChunkMetadata(
            namespace="party-ps",
            source_document="election_manifesto",
        )
        assert cm.fiabilite == Fiabilite.OFFICIAL

    def test_auto_fiabilite_government(self):
        from src.models.chunk_metadata import ChunkMetadata, Fiabilite

        cm = ChunkMetadata(
            namespace="cand-001",
            source_document="profession_de_foi",
        )
        assert cm.fiabilite == Fiabilite.GOVERNMENT

    def test_explicit_fiabilite_not_overridden(self):
        from src.models.chunk_metadata import ChunkMetadata, Fiabilite

        cm = ChunkMetadata(
            namespace="cand-001",
            source_document="election_manifesto",
            fiabilite=Fiabilite.PRESS,  # explicitly set
        )
        assert cm.fiabilite == Fiabilite.PRESS

    def test_defaults(self):
        from src.models.chunk_metadata import ChunkMetadata

        cm = ChunkMetadata(namespace="ns", source_document="candidate_website")
        assert cm.party_ids == []
        assert cm.candidate_ids == []
        assert cm.party_name is None
        assert cm.candidate_name is None
        assert cm.municipality_code is None
        assert cm.page == 0
        assert cm.chunk_index == 0
        assert cm.total_chunks == 0
        assert cm.theme is None
        assert cm.sub_theme is None

    def test_all_fields(self):
        from src.models.chunk_metadata import ChunkMetadata, Fiabilite

        cm = ChunkMetadata(
            namespace="cand-paris-001",
            source_document="profession_de_foi",
            party_ids=["ps"],
            candidate_ids=["cand-paris-001"],
            party_name="Parti Socialiste",
            candidate_name="Marie Dupont",
            municipality_code="75056",
            municipality_name="Paris",
            municipality_postal_code="75000",
            election_type_id="municipales-2026",
            election_year=2026,
            epci_nom="Métropole du Grand Paris",
            epci_code="200054781",
            is_tete_de_liste=True,
            liste_nombre_candidats=69,
            nuance_politique="LGAU",
            is_incumbent=False,
            document_name="Profession de foi Marie Dupont",
            document_id="doc-001",
            url="https://source.fr/doc.pdf",
            document_publish_date="2026-03-01",
            date_scraping="2026-03-10",
            page_title="Programme municipal",
            page_type="pdf",
            page=3,
            chunk_index=7,
            total_chunks=20,
            fiabilite=Fiabilite.GOVERNMENT,
            theme="logement",
            sub_theme="logement social",
        )
        assert cm.municipality_code == "75056"
        assert cm.election_year == 2026
        assert cm.is_tete_de_liste is True
        assert cm.page == 3
        assert cm.chunk_index == 7
        assert cm.theme == "logement"
        assert cm.sub_theme == "logement social"

    def test_invalid_theme_coerced_to_none(self):
        from src.models.chunk_metadata import ChunkMetadata

        cm = ChunkMetadata(
            namespace="ns",
            source_document="election_manifesto",
            theme="not-a-valid-theme",
        )
        assert cm.theme is None

    def test_valid_theme_accepted(self):
        from src.models.chunk_metadata import ChunkMetadata

        cm = ChunkMetadata(
            namespace="ns",
            source_document="election_manifesto",
            theme="economie",
        )
        assert cm.theme == "economie"

    def test_to_qdrant_payload(self):
        from src.models.chunk_metadata import ChunkMetadata, Fiabilite

        cm = ChunkMetadata(
            namespace="ns",
            source_document="election_manifesto",
            theme="education",
        )
        payload = cm.to_qdrant_payload()
        assert isinstance(payload, dict)
        assert payload["namespace"] == "ns"
        assert payload["source_document"] == "election_manifesto"
        # fiabilite is an int in payload
        assert payload["fiabilite"] == int(Fiabilite.OFFICIAL)
        assert isinstance(payload["fiabilite"], int)

    def test_to_qdrant_payload_excludes_none(self):
        from src.models.chunk_metadata import ChunkMetadata

        cm = ChunkMetadata(namespace="ns", source_document="party_website")
        payload = cm.to_qdrant_payload()
        # None fields should be excluded
        assert "party_name" not in payload
        assert "municipality_code" not in payload

    def test_from_qdrant_payload(self):
        from src.models.chunk_metadata import ChunkMetadata, Fiabilite

        payload = {
            "namespace": "party-ps",
            "source_document": "election_manifesto",
            "fiabilite": 2,
            "theme": "economie",
            "page": 1,
            "chunk_index": 3,
            "total_chunks": 10,
        }
        cm = ChunkMetadata.from_qdrant_payload(payload)
        assert cm.namespace == "party-ps"
        assert cm.fiabilite == Fiabilite.OFFICIAL
        assert cm.theme == "economie"
        assert cm.chunk_index == 3

    def test_roundtrip_to_from_qdrant_payload(self):
        from src.models.chunk_metadata import ChunkMetadata

        original = ChunkMetadata(
            namespace="cand-001",
            source_document="profession_de_foi",
            party_ids=["ps"],
            candidate_ids=["cand-001"],
            theme="sante",
            chunk_index=2,
            total_chunks=15,
        )
        payload = original.to_qdrant_payload()
        restored = ChunkMetadata.from_qdrant_payload(payload)
        assert restored.namespace == original.namespace
        assert restored.theme == original.theme
        assert restored.chunk_index == original.chunk_index
        assert restored.fiabilite == original.fiabilite

    def test_missing_required_raises(self):
        from src.models.chunk_metadata import ChunkMetadata

        with pytest.raises(ValidationError):
            ChunkMetadata(namespace="ns")  # source_document missing


# ---------------------------------------------------------------------------
# src/models/scraper.py  (dataclasses — no Pydantic, no ValidationError)
# ---------------------------------------------------------------------------


class TestScrapedPage:
    def test_valid_required_fields(self):
        from src.models.scraper import ScrapedPage

        page = ScrapedPage(
            url="https://example.fr/page",
            title="Accueil",
            content="Bienvenue sur notre site.",
        )
        assert page.url == "https://example.fr/page"
        assert page.title == "Accueil"
        assert page.content == "Bienvenue sur notre site."

    def test_content_length_auto_set(self):
        from src.models.scraper import ScrapedPage

        content = "Hello world!"
        page = ScrapedPage(url="https://x.fr", title="X", content=content)
        assert page.content_length == len(content)

    def test_defaults(self):
        from src.models.scraper import ScrapedPage

        page = ScrapedPage(url="https://x.fr", title="X", content="")
        assert page.page_type == "html"
        assert page.depth == 0
        assert page.content_length == 0

    def test_all_fields(self):
        from src.models.scraper import ScrapedPage

        page = ScrapedPage(
            url="https://x.fr/doc.pdf",
            title="Document PDF",
            content="Contenu PDF long " * 100,
            page_type="pdf",
            depth=2,
        )
        assert page.page_type == "pdf"
        assert page.depth == 2
        assert page.content_length == len("Contenu PDF long " * 100)

    def test_content_length_updated_by_post_init(self):
        from src.models.scraper import ScrapedPage

        page = ScrapedPage(
            url="https://x.fr",
            title="X",
            content="abc",
            content_length=999,  # this gets overridden by __post_init__
        )
        assert page.content_length == 3  # len("abc")

    def test_empty_content(self):
        from src.models.scraper import ScrapedPage

        page = ScrapedPage(url="https://x.fr", title="Empty", content="")
        assert page.content_length == 0


class TestScrapedWebsite:
    def _make_page(self, content="content"):
        from src.models.scraper import ScrapedPage

        return ScrapedPage(url="https://x.fr", title="T", content=content)

    def test_valid_required_fields(self):
        from src.models.scraper import ScrapedWebsite

        sw = ScrapedWebsite(
            candidate_id="cand-001",
            website_url="https://cand-001.fr",
        )
        assert sw.candidate_id == "cand-001"
        assert sw.website_url == "https://cand-001.fr"

    def test_defaults(self):
        from src.models.scraper import ScrapedWebsite

        sw = ScrapedWebsite(
            candidate_id="cand-001",
            website_url="https://cand-001.fr",
        )
        assert sw.pages == []
        assert sw.error is None
        assert sw.stats == {}

    def test_is_successful_false_when_no_pages(self):
        from src.models.scraper import ScrapedWebsite

        sw = ScrapedWebsite(
            candidate_id="cand-001",
            website_url="https://cand-001.fr",
        )
        assert sw.is_successful is False

    def test_is_successful_true_when_has_pages(self):
        from src.models.scraper import ScrapedWebsite

        sw = ScrapedWebsite(
            candidate_id="cand-001",
            website_url="https://cand-001.fr",
            pages=[self._make_page()],
        )
        assert sw.is_successful is True

    def test_total_content_length_zero_when_no_pages(self):
        from src.models.scraper import ScrapedWebsite

        sw = ScrapedWebsite(
            candidate_id="cand-001",
            website_url="https://cand-001.fr",
        )
        assert sw.total_content_length == 0

    def test_total_content_length_sums_pages(self):
        from src.models.scraper import ScrapedWebsite

        pages = [
            self._make_page("abc"),  # len 3
            self._make_page("defgh"),  # len 5
            self._make_page("ij"),  # len 2
        ]
        sw = ScrapedWebsite(
            candidate_id="cand-001",
            website_url="https://cand-001.fr",
            pages=pages,
        )
        assert sw.total_content_length == 10

    def test_with_error(self):
        from src.models.scraper import ScrapedWebsite

        sw = ScrapedWebsite(
            candidate_id="cand-002",
            website_url="https://broken.fr",
            error="Connection timeout",
        )
        assert sw.error == "Connection timeout"
        assert sw.is_successful is False

    def test_with_stats(self):
        from src.models.scraper import ScrapedWebsite

        sw = ScrapedWebsite(
            candidate_id="cand-003",
            website_url="https://cand-003.fr",
            pages=[self._make_page()],
            stats={"html": 3, "pdf": 1},
        )
        assert sw.stats["html"] == 3
        assert sw.stats["pdf"] == 1
        assert sw.is_successful is True
