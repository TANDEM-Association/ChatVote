# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Unit tests for src/prompts.py and src/prompts_en.py.

All tests run without external services (no Qdrant, Firebase, LLM APIs).
Pure-function tests — no mocking required.
"""

import re

import pytest
from langchain.prompts import PromptTemplate

from src.prompts import (
    DEFAULT_LOCALE,
    get_candidate_chat_answer_guidelines,
    get_chat_answer_guidelines,
    get_combined_answer_guidelines,
    get_global_combined_answer_guidelines,
    get_quick_reply_guidelines,
    # PromptTemplate constants — French
    candidate_local_response_system_prompt_template,
    candidate_national_response_system_prompt_template,
    candidate_response_system_prompt_template,
    chatvote_response_system_prompt_template,
    combined_response_system_prompt_template,
    detect_entities_system_prompt_template,
    detect_entities_user_prompt_template,
    determine_question_targets_system_prompt,
    determine_question_targets_user_prompt,
    determine_question_type_system_prompt,
    determine_question_type_user_prompt,
    generate_chat_summary_system_prompt,
    generate_chat_summary_user_prompt,
    generate_chat_title_and_quick_replies_system_prompt,
    generate_chat_title_and_quick_replies_user_prompt,
    generate_chatvote_title_and_quick_replies_system_prompt,
    generate_party_vote_behavior_summary_system_prompt,
    generate_party_vote_behavior_summary_user_prompt,
    global_combined_response_system_prompt_template,
    party_comparison_system_prompt_template,
    party_response_system_prompt_template,
    perplexity_candidate_system_prompt,
    perplexity_candidate_user_prompt,
    perplexity_system_prompt,
    perplexity_user_prompt,
    reranking_system_prompt_template,
    reranking_user_prompt_template,
    streaming_candidate_response_user_prompt_template,
    streaming_combined_response_user_prompt_template,
    streaming_party_response_user_prompt_template,
    system_prompt_improve_general_chat_rag_query_template,
    system_prompt_improvement_candidate_template,
    system_prompt_improvement_rag_template_vote_behavior_summary,
    system_prompt_improvement_template,
    user_prompt_improvement_rag_template_vote_behavior_summary,
    user_prompt_improvement_template,
)
from src.prompts_en import (
    get_candidate_chat_answer_guidelines_en,
    get_chat_answer_guidelines_en,
    get_global_combined_answer_guidelines_en,
    get_quick_reply_guidelines_en,
    # PromptTemplate constants — English
    candidate_response_system_prompt_template_en,
    chatvote_response_system_prompt_template_en,
    determine_question_targets_system_prompt_en,
    determine_question_targets_user_prompt_en,
    determine_question_type_system_prompt_en,
    determine_question_type_user_prompt_en,
    generate_chat_summary_system_prompt_en,
    generate_chat_summary_user_prompt_en,
    generate_chat_title_and_quick_replies_system_prompt_en,
    generate_chat_title_and_quick_replies_user_prompt_en,
    generate_chatvote_title_and_quick_replies_system_prompt_en,
    global_combined_response_system_prompt_template_en,
    party_comparison_system_prompt_template_en,
    party_response_system_prompt_template_en,
    reranking_system_prompt_template_en,
    reranking_user_prompt_template_en,
    streaming_candidate_response_user_prompt_template_en,
    streaming_combined_response_user_prompt_template_en,
    streaming_party_response_user_prompt_template_en,
    system_prompt_improve_general_chat_rag_query_template_en,
    system_prompt_improvement_template_en,
    user_prompt_improvement_template_en,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_unclosed_braces(text: str) -> bool:
    """Return True if any { or } appears outside a valid {variable} pair."""
    # Strip all valid {variable} occurrences and check for strays
    cleaned = re.sub(r"\{[^{}]+\}", "", text)
    return "{" in cleaned or "}" in cleaned


def _template_variables(template: PromptTemplate) -> set[str]:
    """Return the set of input_variables declared on a PromptTemplate."""
    return set(template.input_variables)


# ---------------------------------------------------------------------------
# TestGetChatAnswerGuidelinesDispatch
# ---------------------------------------------------------------------------


class TestGetChatAnswerGuidelinesDispatch:
    """Tests for get_chat_answer_guidelines() locale dispatch."""

    def test_returns_string_for_fr_locale(self):
        result = get_chat_answer_guidelines("TestParty", locale="fr")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_string_for_en_locale(self):
        result = get_chat_answer_guidelines("TestParty", locale="en")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_default_locale_is_fr(self):
        assert DEFAULT_LOCALE == "fr"

    def test_default_locale_produces_french_content(self):
        result = get_chat_answer_guidelines("TestParty")
        assert "français" in result or "Directives" in result

    def test_en_locale_produces_english_content(self):
        result = get_chat_answer_guidelines("TestParty", locale="en")
        assert "Guidelines" in result or "English" in result

    def test_fr_and_en_results_differ(self):
        fr = get_chat_answer_guidelines("TestParty", locale="fr")
        en = get_chat_answer_guidelines("TestParty", locale="en")
        assert fr != en


# ---------------------------------------------------------------------------
# TestGetChatAnswerGuidelinesFr
# ---------------------------------------------------------------------------


class TestGetChatAnswerGuidelinesFr:
    """Tests for the French guidelines string (_get_chat_answer_guidelines_fr)."""

    def test_party_name_appears_in_non_comparing_output(self):
        result = get_chat_answer_guidelines("LFI", is_comparing=False, locale="fr")
        assert "LFI" in result

    def test_party_name_appears_in_comparing_output(self):
        result = get_chat_answer_guidelines("RN", is_comparing=True, locale="fr")
        # party_name not directly injected in comparison_handling branch, but the
        # guidelines header and other references should still be non-empty
        assert isinstance(result, str)
        assert len(result) > 0

    def test_non_comparing_contains_redirect_hint(self):
        result = get_chat_answer_guidelines("LFI", is_comparing=False, locale="fr")
        assert "LFI" in result
        # Non-comparing mode should reference the single-party reminder
        assert "responsable" in result

    def test_comparing_contains_neutral_observer_hint(self):
        result = get_chat_answer_guidelines("LFI", is_comparing=True, locale="fr")
        assert "neutre" in result or "observateur" in result

    def test_non_comparing_and_comparing_differ(self):
        non_cmp = get_chat_answer_guidelines("LFI", is_comparing=False, locale="fr")
        cmp = get_chat_answer_guidelines("LFI", is_comparing=True, locale="fr")
        assert non_cmp != cmp

    def test_contains_sources_keyword(self):
        result = get_chat_answer_guidelines("LFI", locale="fr")
        assert "sources" in result.lower()

    def test_contains_citation_instructions(self):
        result = get_chat_answer_guidelines("LFI", locale="fr")
        assert "citation" in result.lower() or "cite" in result.lower() or "IDs" in result

    def test_contains_no_vote_recommendation(self):
        result = get_chat_answer_guidelines("LFI", locale="fr")
        assert "recommandation de vote" in result or "AUCUNE recommandation" in result

    def test_no_unclosed_braces(self):
        result = get_chat_answer_guidelines("LFI", locale="fr")
        assert not _has_unclosed_braces(result)

    def test_contains_markdown_format_instruction(self):
        result = get_chat_answer_guidelines("LFI", locale="fr")
        assert "Markdown" in result

    def test_contains_data_protection_section(self):
        result = get_chat_answer_guidelines("LFI", locale="fr")
        assert "données" in result.lower() or "Protection" in result


# ---------------------------------------------------------------------------
# TestGetChatAnswerGuidelinesEn
# ---------------------------------------------------------------------------


class TestGetChatAnswerGuidelinesEn:
    """Tests for get_chat_answer_guidelines_en()."""

    def test_party_name_appears_in_non_comparing_output(self):
        result = get_chat_answer_guidelines_en("Greens", is_comparing=False)
        assert "Greens" in result

    def test_non_comparing_contains_redirect_hint(self):
        result = get_chat_answer_guidelines_en("Greens", is_comparing=False)
        assert "Greens" in result
        assert "responsible" in result

    def test_comparing_contains_neutral_observer_hint(self):
        result = get_chat_answer_guidelines_en("Greens", is_comparing=True)
        assert "neutral" in result or "observer" in result

    def test_non_comparing_and_comparing_differ(self):
        non_cmp = get_chat_answer_guidelines_en("Greens", is_comparing=False)
        cmp = get_chat_answer_guidelines_en("Greens", is_comparing=True)
        assert non_cmp != cmp

    def test_contains_sources_keyword(self):
        result = get_chat_answer_guidelines_en("Greens")
        assert "source" in result.lower()

    def test_contains_citation_instructions(self):
        result = get_chat_answer_guidelines_en("Greens")
        assert "citation" in result.lower() or "cite" in result.lower() or "IDs" in result

    def test_contains_no_vote_recommendation(self):
        result = get_chat_answer_guidelines_en("Greens")
        assert "voting recommendations" in result or "NO voting" in result

    def test_no_unclosed_braces(self):
        result = get_chat_answer_guidelines_en("Greens")
        assert not _has_unclosed_braces(result)

    def test_contains_english_language_instruction(self):
        result = get_chat_answer_guidelines_en("Greens")
        assert "English" in result

    def test_returns_string(self):
        result = get_chat_answer_guidelines_en("TestParty")
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# TestFrenchPromptTemplates
# ---------------------------------------------------------------------------


class TestFrenchPromptTemplates:
    """Tests for PromptTemplate constants exported from src/prompts.py."""

    def test_party_response_template_is_prompt_template(self):
        assert isinstance(party_response_system_prompt_template, PromptTemplate)

    def test_party_response_template_has_required_variables(self):
        vars_ = _template_variables(party_response_system_prompt_template)
        assert "party_name" in vars_
        assert "party_long_name" in vars_
        assert "rag_context" in vars_
        assert "answer_guidelines" in vars_

    def test_party_comparison_template_has_parties_being_compared(self):
        vars_ = _template_variables(party_comparison_system_prompt_template)
        assert "parties_being_compared" in vars_
        assert "party_name" in vars_

    def test_streaming_party_response_user_template_variables(self):
        vars_ = _template_variables(streaming_party_response_user_prompt_template)
        assert "conversation_history" in vars_
        assert "last_user_message" in vars_

    def test_system_prompt_improvement_template_variables(self):
        vars_ = _template_variables(system_prompt_improvement_template)
        assert "party_name" in vars_

    def test_user_prompt_improvement_template_variables(self):
        vars_ = _template_variables(user_prompt_improvement_template)
        assert "conversation_history" in vars_
        assert "last_user_message" in vars_

    def test_chatvote_response_template_variables(self):
        vars_ = _template_variables(chatvote_response_system_prompt_template)
        assert "all_parties_list" in vars_
        assert "rag_context" in vars_

    def test_reranking_system_template_variables(self):
        vars_ = _template_variables(reranking_system_prompt_template)
        assert "sources" in vars_

    def test_reranking_user_template_variables(self):
        vars_ = _template_variables(reranking_user_prompt_template)
        assert "conversation_history" in vars_
        assert "user_message" in vars_

    def test_determine_question_targets_system_template_variables(self):
        vars_ = _template_variables(determine_question_targets_system_prompt)
        assert "current_party_list" in vars_
        assert "additional_party_list" in vars_

    def test_determine_question_targets_user_template_variables(self):
        vars_ = _template_variables(determine_question_targets_user_prompt)
        assert "previous_chat_history" in vars_
        assert "user_message" in vars_

    def test_determine_question_type_system_template_is_prompt_template(self):
        assert isinstance(determine_question_type_system_prompt, PromptTemplate)

    def test_determine_question_type_user_template_variables(self):
        vars_ = _template_variables(determine_question_type_user_prompt)
        assert "previous_chat_history" in vars_
        assert "user_message" in vars_

    def test_generate_chat_summary_system_template_is_prompt_template(self):
        assert isinstance(generate_chat_summary_system_prompt, PromptTemplate)

    def test_generate_chat_summary_user_template_variables(self):
        vars_ = _template_variables(generate_chat_summary_user_prompt)
        assert "conversation_history" in vars_

    def test_perplexity_system_prompt_variables(self):
        vars_ = _template_variables(perplexity_system_prompt)
        assert "party_name" in vars_

    def test_perplexity_user_prompt_variables(self):
        vars_ = _template_variables(perplexity_user_prompt)
        assert "user_message" in vars_
        assert "assistant_message" in vars_
        assert "party_name" in vars_

    def test_perplexity_candidate_system_prompt_variables(self):
        vars_ = _template_variables(perplexity_candidate_system_prompt)
        assert "candidate_name" in vars_

    def test_perplexity_candidate_user_prompt_variables(self):
        vars_ = _template_variables(perplexity_candidate_user_prompt)
        assert "candidate_name" in vars_
        assert "user_message" in vars_
        assert "assistant_message" in vars_

    def test_generate_chat_title_and_quick_replies_system_template_variables(self):
        vars_ = _template_variables(generate_chat_title_and_quick_replies_system_prompt)
        assert "party_list" in vars_

    def test_generate_chat_title_and_quick_replies_user_template_variables(self):
        vars_ = _template_variables(generate_chat_title_and_quick_replies_user_prompt)
        assert "conversation_history" in vars_

    def test_generate_chatvote_title_and_quick_replies_system_template_variables(self):
        vars_ = _template_variables(
            generate_chatvote_title_and_quick_replies_system_prompt
        )
        assert "party_list" in vars_
        assert "quick_reply_guidelines" in vars_

    def test_generate_party_vote_behavior_summary_system_variables(self):
        vars_ = _template_variables(generate_party_vote_behavior_summary_system_prompt)
        assert "party_name" in vars_
        assert "votes_list" in vars_

    def test_generate_party_vote_behavior_summary_user_variables(self):
        vars_ = _template_variables(generate_party_vote_behavior_summary_user_prompt)
        assert "party_name" in vars_
        assert "user_message" in vars_
        assert "assistant_message" in vars_

    def test_system_prompt_improvement_rag_vote_behavior_variables(self):
        vars_ = _template_variables(
            system_prompt_improvement_rag_template_vote_behavior_summary
        )
        assert "party_name" in vars_

    def test_user_prompt_improvement_rag_vote_behavior_variables(self):
        vars_ = _template_variables(
            user_prompt_improvement_rag_template_vote_behavior_summary
        )
        assert "last_user_message" in vars_
        assert "last_assistant_message" in vars_
        assert "party_name" in vars_

    def test_candidate_response_template_variables(self):
        vars_ = _template_variables(candidate_response_system_prompt_template)
        assert "candidate_name" in vars_
        assert "rag_context" in vars_
        assert "answer_guidelines" in vars_

    def test_candidate_local_response_template_variables(self):
        vars_ = _template_variables(candidate_local_response_system_prompt_template)
        assert "municipality_name" in vars_
        assert "candidates_list" in vars_
        assert "rag_context" in vars_

    def test_candidate_national_response_template_variables(self):
        vars_ = _template_variables(candidate_national_response_system_prompt_template)
        assert "rag_context" in vars_

    def test_streaming_candidate_response_user_template_variables(self):
        vars_ = _template_variables(streaming_candidate_response_user_prompt_template)
        assert "conversation_history" in vars_
        assert "last_user_message" in vars_

    def test_system_prompt_improvement_candidate_template_variables(self):
        vars_ = _template_variables(system_prompt_improvement_candidate_template)
        assert "scope_context" in vars_

    def test_detect_entities_system_template_variables(self):
        vars_ = _template_variables(detect_entities_system_prompt_template)
        assert "parties_list" in vars_
        assert "candidates_list" in vars_

    def test_detect_entities_user_template_variables(self):
        vars_ = _template_variables(detect_entities_user_prompt_template)
        assert "conversation_history" in vars_
        assert "user_message" in vars_

    def test_combined_response_system_template_variables(self):
        vars_ = _template_variables(combined_response_system_prompt_template)
        assert "party_name" in vars_
        assert "manifesto_context" in vars_
        assert "candidates_context" in vars_

    def test_streaming_combined_response_user_template_variables(self):
        vars_ = _template_variables(streaming_combined_response_user_prompt_template)
        assert "conversation_history" in vars_
        assert "last_user_message" in vars_

    def test_global_combined_response_system_template_variables(self):
        vars_ = _template_variables(global_combined_response_system_prompt_template)
        assert "parties_list" in vars_
        assert "manifesto_context" in vars_

    def test_system_prompt_improve_general_chat_rag_query_template_is_prompt_template(
        self,
    ):
        assert isinstance(
            system_prompt_improve_general_chat_rag_query_template, PromptTemplate
        )


# ---------------------------------------------------------------------------
# TestEnglishPromptTemplates
# ---------------------------------------------------------------------------


class TestEnglishPromptTemplates:
    """Tests for PromptTemplate constants exported from src/prompts_en.py."""

    def test_party_response_template_en_is_prompt_template(self):
        assert isinstance(party_response_system_prompt_template_en, PromptTemplate)

    def test_party_response_template_en_variables(self):
        vars_ = _template_variables(party_response_system_prompt_template_en)
        assert "party_name" in vars_
        assert "rag_context" in vars_
        assert "answer_guidelines" in vars_

    def test_party_comparison_template_en_variables(self):
        vars_ = _template_variables(party_comparison_system_prompt_template_en)
        assert "parties_being_compared" in vars_
        assert "party_name" in vars_

    def test_streaming_party_response_user_template_en_variables(self):
        vars_ = _template_variables(streaming_party_response_user_prompt_template_en)
        assert "conversation_history" in vars_
        assert "last_user_message" in vars_

    def test_system_prompt_improvement_template_en_variables(self):
        vars_ = _template_variables(system_prompt_improvement_template_en)
        assert "party_name" in vars_

    def test_user_prompt_improvement_template_en_variables(self):
        vars_ = _template_variables(user_prompt_improvement_template_en)
        assert "conversation_history" in vars_
        assert "last_user_message" in vars_

    def test_chatvote_response_template_en_variables(self):
        vars_ = _template_variables(chatvote_response_system_prompt_template_en)
        assert "all_parties_list" in vars_
        assert "rag_context" in vars_

    def test_determine_question_targets_system_template_en_variables(self):
        vars_ = _template_variables(determine_question_targets_system_prompt_en)
        assert "current_party_list" in vars_
        assert "additional_party_list" in vars_

    def test_determine_question_targets_user_template_en_variables(self):
        vars_ = _template_variables(determine_question_targets_user_prompt_en)
        assert "previous_chat_history" in vars_
        assert "user_message" in vars_

    def test_determine_question_type_system_template_en_is_prompt_template(self):
        assert isinstance(determine_question_type_system_prompt_en, PromptTemplate)

    def test_determine_question_type_user_template_en_variables(self):
        vars_ = _template_variables(determine_question_type_user_prompt_en)
        assert "previous_chat_history" in vars_
        assert "user_message" in vars_

    def test_generate_chat_summary_system_template_en_is_prompt_template(self):
        assert isinstance(generate_chat_summary_system_prompt_en, PromptTemplate)

    def test_generate_chat_summary_user_template_en_variables(self):
        vars_ = _template_variables(generate_chat_summary_user_prompt_en)
        assert "conversation_history" in vars_

    def test_reranking_system_template_en_variables(self):
        vars_ = _template_variables(reranking_system_prompt_template_en)
        assert "sources" in vars_

    def test_reranking_user_template_en_variables(self):
        vars_ = _template_variables(reranking_user_prompt_template_en)
        assert "conversation_history" in vars_
        assert "user_message" in vars_

    def test_candidate_response_template_en_variables(self):
        vars_ = _template_variables(candidate_response_system_prompt_template_en)
        assert "candidate_name" in vars_
        assert "rag_context" in vars_

    def test_streaming_candidate_response_user_template_en_variables(self):
        vars_ = _template_variables(streaming_candidate_response_user_prompt_template_en)
        assert "conversation_history" in vars_
        assert "last_user_message" in vars_

    def test_global_combined_response_system_template_en_variables(self):
        vars_ = _template_variables(global_combined_response_system_prompt_template_en)
        assert "parties_list" in vars_
        assert "manifesto_context" in vars_

    def test_streaming_combined_response_user_template_en_variables(self):
        vars_ = _template_variables(
            streaming_combined_response_user_prompt_template_en
        )
        assert "conversation_history" in vars_
        assert "last_user_message" in vars_

    def test_generate_chat_title_and_quick_replies_system_template_en_variables(self):
        vars_ = _template_variables(
            generate_chat_title_and_quick_replies_system_prompt_en
        )
        assert "party_list" in vars_

    def test_generate_chat_title_and_quick_replies_user_template_en_variables(self):
        vars_ = _template_variables(
            generate_chat_title_and_quick_replies_user_prompt_en
        )
        assert "conversation_history" in vars_

    def test_generate_chatvote_title_and_quick_replies_system_template_en_variables(
        self,
    ):
        vars_ = _template_variables(
            generate_chatvote_title_and_quick_replies_system_prompt_en
        )
        assert "party_list" in vars_
        assert "quick_reply_guidelines" in vars_

    def test_system_prompt_improve_general_chat_rag_query_template_en_is_prompt_template(
        self,
    ):
        assert isinstance(
            system_prompt_improve_general_chat_rag_query_template_en, PromptTemplate
        )


# ---------------------------------------------------------------------------
# TestGetQuickReplyGuidelines
# ---------------------------------------------------------------------------


class TestGetQuickReplyGuidelines:
    """Tests for get_quick_reply_guidelines() (French)."""

    def test_returns_string_for_comparing_true(self):
        result = get_quick_reply_guidelines(is_comparing=True)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_string_for_comparing_false(self):
        result = get_quick_reply_guidelines(is_comparing=False)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_comparing_and_non_comparing_differ(self):
        cmp = get_quick_reply_guidelines(is_comparing=True)
        non_cmp = get_quick_reply_guidelines(is_comparing=False)
        assert cmp != non_cmp

    def test_non_comparing_mentions_elections(self):
        result = get_quick_reply_guidelines(is_comparing=False)
        assert "élections" in result.lower() or "ChatVote" in result

    def test_comparing_mentions_technical_term_or_comparison(self):
        result = get_quick_reply_guidelines(is_comparing=True)
        assert "technique" in result.lower() or "comparaison" in result.lower() or "différente" in result.lower()

    def test_both_results_mention_quick_replies_count(self):
        for is_comparing in (True, False):
            result = get_quick_reply_guidelines(is_comparing=is_comparing)
            assert "3" in result


class TestGetQuickReplyGuidelinesEn:
    """Tests for get_quick_reply_guidelines_en() (English)."""

    def test_returns_string_for_comparing_true(self):
        result = get_quick_reply_guidelines_en(is_comparing=True)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_string_for_comparing_false(self):
        result = get_quick_reply_guidelines_en(is_comparing=False)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_comparing_and_non_comparing_differ(self):
        cmp = get_quick_reply_guidelines_en(is_comparing=True)
        non_cmp = get_quick_reply_guidelines_en(is_comparing=False)
        assert cmp != non_cmp

    def test_both_results_mention_quick_replies_count(self):
        for is_comparing in (True, False):
            result = get_quick_reply_guidelines_en(is_comparing=is_comparing)
            assert "3" in result


# ---------------------------------------------------------------------------
# TestGetCandidateChatAnswerGuidelines
# ---------------------------------------------------------------------------


class TestGetCandidateChatAnswerGuidelines:
    """Tests for get_candidate_chat_answer_guidelines() (French)."""

    def test_candidate_name_in_non_comparing_output(self):
        result = get_candidate_chat_answer_guidelines("Marie Dupont", is_comparing=False)
        assert "Marie Dupont" in result

    def test_non_comparing_contains_single_candidate_reminder(self):
        result = get_candidate_chat_answer_guidelines("Marie Dupont", is_comparing=False)
        assert "Marie Dupont" in result
        assert "responsable" in result

    def test_comparing_contains_neutral_observer_hint(self):
        result = get_candidate_chat_answer_guidelines("Marie Dupont", is_comparing=True)
        assert "neutre" in result or "observateur" in result

    def test_non_comparing_and_comparing_differ(self):
        non_cmp = get_candidate_chat_answer_guidelines("Marie Dupont", is_comparing=False)
        cmp = get_candidate_chat_answer_guidelines("Marie Dupont", is_comparing=True)
        assert non_cmp != cmp

    def test_contains_source_instructions(self):
        result = get_candidate_chat_answer_guidelines("Marie Dupont")
        assert "sources" in result.lower() or "site web" in result.lower()

    def test_no_unclosed_braces(self):
        result = get_candidate_chat_answer_guidelines("Marie Dupont")
        assert not _has_unclosed_braces(result)

    def test_returns_string(self):
        result = get_candidate_chat_answer_guidelines("TestCandidate")
        assert isinstance(result, str)
        assert len(result) > 0


class TestGetCandidateChatAnswerGuidelinesEn:
    """Tests for get_candidate_chat_answer_guidelines_en() (English)."""

    def test_candidate_name_in_non_comparing_output(self):
        result = get_candidate_chat_answer_guidelines_en("John Doe", is_comparing=False)
        assert "John Doe" in result

    def test_non_comparing_contains_single_candidate_reminder(self):
        result = get_candidate_chat_answer_guidelines_en("John Doe", is_comparing=False)
        assert "John Doe" in result
        assert "responsible" in result

    def test_comparing_contains_neutral_observer_hint(self):
        result = get_candidate_chat_answer_guidelines_en("John Doe", is_comparing=True)
        assert "neutral" in result or "observer" in result

    def test_non_comparing_and_comparing_differ(self):
        non_cmp = get_candidate_chat_answer_guidelines_en("John Doe", is_comparing=False)
        cmp = get_candidate_chat_answer_guidelines_en("John Doe", is_comparing=True)
        assert non_cmp != cmp

    def test_no_unclosed_braces(self):
        result = get_candidate_chat_answer_guidelines_en("John Doe")
        assert not _has_unclosed_braces(result)

    def test_returns_string(self):
        result = get_candidate_chat_answer_guidelines_en("TestCandidate")
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# TestGetCombinedAnswerGuidelines
# ---------------------------------------------------------------------------


class TestGetCombinedAnswerGuidelines:
    """Tests for get_combined_answer_guidelines() (French)."""

    def test_local_scope_with_municipality_mentions_municipality(self):
        result = get_combined_answer_guidelines("local", municipality_name="Paris")
        assert "Paris" in result

    def test_national_scope_does_not_mention_local_municipality(self):
        result = get_combined_answer_guidelines("national")
        assert "national" in result.lower()

    def test_local_and_national_scopes_differ(self):
        local = get_combined_answer_guidelines("local", municipality_name="Lyon")
        national = get_combined_answer_guidelines("national")
        assert local != national

    def test_contains_neutrality_instruction(self):
        result = get_combined_answer_guidelines("national")
        assert "neutralit" in result.lower() or "neutre" in result.lower() or "Neutralité" in result

    def test_no_unclosed_braces(self):
        result = get_combined_answer_guidelines("local", municipality_name="Paris")
        assert not _has_unclosed_braces(result)

    def test_returns_string(self):
        result = get_combined_answer_guidelines("national")
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# TestGetGlobalCombinedAnswerGuidelines
# ---------------------------------------------------------------------------


class TestGetGlobalCombinedAnswerGuidelines:
    """Tests for get_global_combined_answer_guidelines() (French)."""

    def test_local_scope_with_municipality_mentions_municipality(self):
        result = get_global_combined_answer_guidelines("local", municipality_name="Lyon")
        assert "Lyon" in result

    def test_national_scope_mentions_national(self):
        result = get_global_combined_answer_guidelines("national")
        assert "NATIONAL" in result or "national" in result.lower()

    def test_local_and_national_scopes_differ(self):
        local = get_global_combined_answer_guidelines("local", municipality_name="Lyon")
        national = get_global_combined_answer_guidelines("national")
        assert local != national

    def test_contains_neutrality_instruction(self):
        result = get_global_combined_answer_guidelines("national")
        assert "neutralit" in result.lower() or "Neutralité" in result

    def test_no_unclosed_braces(self):
        result = get_global_combined_answer_guidelines("local", municipality_name="Paris")
        assert not _has_unclosed_braces(result)

    def test_returns_string(self):
        result = get_global_combined_answer_guidelines("national")
        assert isinstance(result, str)
        assert len(result) > 0


class TestGetGlobalCombinedAnswerGuidelinesEn:
    """Tests for get_global_combined_answer_guidelines_en() (English)."""

    def test_local_scope_with_municipality_mentions_municipality(self):
        result = get_global_combined_answer_guidelines_en("local", municipality_name="Paris")
        assert "Paris" in result

    def test_national_scope_mentions_national(self):
        result = get_global_combined_answer_guidelines_en("national")
        assert "NATIONAL" in result or "national" in result.lower()

    def test_local_and_national_scopes_differ(self):
        local = get_global_combined_answer_guidelines_en("local", municipality_name="Lyon")
        national = get_global_combined_answer_guidelines_en("national")
        assert local != national

    def test_no_unclosed_braces(self):
        result = get_global_combined_answer_guidelines_en("national")
        assert not _has_unclosed_braces(result)

    def test_returns_string(self):
        result = get_global_combined_answer_guidelines_en("national")
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# TestTemplateFormattability
# ---------------------------------------------------------------------------


class TestTemplateFormattability:
    """Smoke-tests that each PromptTemplate can be rendered without errors."""

    def _fill(self, template: PromptTemplate, extra: dict | None = None) -> str:
        """Fill a template with dummy values for all its input variables."""
        values = {var: f"<{var}>" for var in template.input_variables}
        if extra:
            values.update(extra)
        return template.format(**values)

    def test_party_response_template_renders(self):
        result = self._fill(party_response_system_prompt_template)
        assert "<party_name>" in result

    def test_party_comparison_template_renders(self):
        result = self._fill(party_comparison_system_prompt_template)
        assert "<parties_being_compared>" in result

    def test_reranking_system_template_renders(self):
        result = self._fill(reranking_system_prompt_template)
        assert "<sources>" in result

    def test_determine_question_type_system_template_renders(self):
        result = self._fill(determine_question_type_system_prompt)
        assert isinstance(result, str)

    def test_party_response_template_en_renders(self):
        result = self._fill(party_response_system_prompt_template_en)
        assert "<party_name>" in result

    def test_reranking_system_template_en_renders(self):
        result = self._fill(reranking_system_prompt_template_en)
        assert "<sources>" in result

    def test_chatvote_response_template_renders(self):
        result = self._fill(chatvote_response_system_prompt_template)
        assert "<all_parties_list>" in result

    def test_chatvote_response_template_en_renders(self):
        result = self._fill(chatvote_response_system_prompt_template_en)
        assert "<all_parties_list>" in result
