# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Unit tests for src/i18n/translator.py.

All tests run without external services (no Qdrant, Firebase, LLM APIs).
"""

import pytest

from src.i18n.translator import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    _load_translations,
    _translations_cache,
    clear_cache,
    get_supported_locales,
    get_text,
    is_valid_locale,
    normalize_locale,
)


@pytest.fixture(autouse=True)
def clear_translation_cache():
    """Ensure a clean cache state before and after every test."""
    _translations_cache.clear()
    yield
    _translations_cache.clear()


# ---------------------------------------------------------------------------
# get_text() — French locale
# ---------------------------------------------------------------------------


class TestGetTextFrench:
    def test_top_level_key(self):
        result = get_text("welcome", "fr")
        assert result == "Bienvenue sur l'API ChatVote"

    def test_nested_key_errors_generic(self):
        result = get_text("errors.generic", "fr")
        assert result == "Désolé, une erreur s'est produite. Veuillez réessayer plus tard."

    def test_nested_key_errors_cannot_answer(self):
        result = get_text("errors.cannot_answer", "fr")
        assert result == "Je ne peux malheureusement pas répondre à cette question."

    def test_nested_key_errors_session_not_started(self):
        result = get_text("errors.session_not_started", "fr")
        assert result == "Il semble que la session de chat n'a pas été démarrée."

    def test_nested_key_errors_timeout_party_documents(self):
        result = get_text("errors.timeout_party_documents", "fr")
        assert result == "Délai d'attente dépassé lors de la récupération des documents."

    def test_nested_key_errors_timeout_party_responses(self):
        result = get_text("errors.timeout_party_responses", "fr")
        assert result == "Délai d'attente dépassé lors de la récupération des réponses."

    def test_nested_key_errors_validation_error(self):
        result = get_text("errors.validation_error", "fr")
        assert result == "Erreur de validation des données."

    def test_nested_key_chat_summary_placeholder(self):
        result = get_text("chat.summary_placeholder", "fr")
        assert result == "Un résumé devrait apparaître ici..."

    def test_nested_key_chat_no_title(self):
        result = get_text("chat.no_title", "fr")
        assert result == "Aucun titre attribué"

    def test_nested_key_chat_default_title(self):
        result = get_text("chat.default_title", "fr")
        assert result == "Discussion politique"

    def test_nested_key_rag_no_info_found(self):
        result = get_text("rag.no_info_found", "fr")
        assert result == "Aucune information pertinente trouvée dans la collection de documents."

    def test_nested_key_rag_no_candidate_info(self):
        result = get_text("rag.no_candidate_info", "fr")
        assert result == "Aucune information pertinente trouvée sur les sites web des candidats."

    def test_nested_key_rag_no_manifesto_info(self):
        result = get_text("rag.no_manifesto_info", "fr")
        assert result == "Aucune information trouvée dans les programmes officiels."

    def test_nested_key_voting_behavior_no_votes_found(self):
        result = get_text("voting_behavior.no_votes_found", "fr")
        assert result == "Aucun vote correspondant trouvé."

    def test_nested_key_voting_behavior_cannot_provide_info(self):
        result = get_text("voting_behavior.cannot_provide_info", "fr")
        assert result == "Je ne peux malheureusement pas fournir d'informations à ce sujet."

    def test_nested_key_prompts_response_language(self):
        result = get_text("prompts.response_language", "fr")
        assert result == "Réponds exclusivement en français."

    def test_nested_key_prompts_use_simple_language(self):
        result = get_text("prompts.use_simple_language", "fr")
        assert result == "Utilise un français simple et explique brièvement les termes techniques."

    def test_default_locale_is_french(self):
        """get_text() with no locale argument should use DEFAULT_LOCALE ('fr')."""
        assert DEFAULT_LOCALE == "fr"
        result = get_text("welcome")
        assert result == "Bienvenue sur l'API ChatVote"


# ---------------------------------------------------------------------------
# get_text() — English locale
# ---------------------------------------------------------------------------


class TestGetTextEnglish:
    def test_top_level_key(self):
        result = get_text("welcome", "en")
        assert result == "Welcome to the ChatVote API"

    def test_nested_key_errors_generic(self):
        result = get_text("errors.generic", "en")
        assert result == "Sorry, an error occurred. Please try again later."

    def test_nested_key_errors_cannot_answer(self):
        result = get_text("errors.cannot_answer", "en")
        assert result == "Unfortunately, I cannot answer this question."

    def test_nested_key_errors_session_not_started(self):
        result = get_text("errors.session_not_started", "en")
        assert result == "It seems the chat session has not been started."

    def test_nested_key_errors_timeout_party_documents(self):
        result = get_text("errors.timeout_party_documents", "en")
        assert result == "Timeout while fetching the documents."

    def test_nested_key_errors_timeout_party_responses(self):
        result = get_text("errors.timeout_party_responses", "en")
        assert result == "Timeout while fetching the responses."

    def test_nested_key_errors_validation_error(self):
        result = get_text("errors.validation_error", "en")
        assert result == "Data validation error."

    def test_nested_key_chat_summary_placeholder(self):
        result = get_text("chat.summary_placeholder", "en")
        assert result == "A summary should appear here..."

    def test_nested_key_chat_no_title(self):
        result = get_text("chat.no_title", "en")
        assert result == "No title assigned"

    def test_nested_key_chat_default_title(self):
        result = get_text("chat.default_title", "en")
        assert result == "Political discussion"

    def test_nested_key_rag_no_info_found(self):
        result = get_text("rag.no_info_found", "en")
        assert result == "No relevant information found in the document collection."

    def test_nested_key_rag_no_candidate_info(self):
        result = get_text("rag.no_candidate_info", "en")
        assert result == "No relevant information found on candidate websites."

    def test_nested_key_rag_no_manifesto_info(self):
        result = get_text("rag.no_manifesto_info", "en")
        assert result == "No information found in official programs."

    def test_nested_key_voting_behavior_no_votes_found(self):
        result = get_text("voting_behavior.no_votes_found", "en")
        assert result == "No matching votes found."

    def test_nested_key_voting_behavior_cannot_provide_info(self):
        result = get_text("voting_behavior.cannot_provide_info", "en")
        assert result == "Unfortunately, I cannot provide information on this topic."

    def test_nested_key_prompts_response_language(self):
        result = get_text("prompts.response_language", "en")
        assert result == "Respond exclusively in English."

    def test_nested_key_prompts_use_simple_language(self):
        result = get_text("prompts.use_simple_language", "en")
        assert result == "Use simple English and briefly explain technical terms."

    def test_fr_and_en_differ_for_same_key(self):
        """Sanity check: translations are actually locale-specific."""
        fr_result = get_text("welcome", "fr")
        en_result = get_text("welcome", "en")
        assert fr_result != en_result


# ---------------------------------------------------------------------------
# get_text() — kwargs variable substitution
# ---------------------------------------------------------------------------


class TestGetTextKwargsSubstitution:
    def test_substitutes_single_kwarg(self, tmp_path, monkeypatch):
        """Variables in {placeholder} syntax are interpolated."""
        import json
        from src.i18n import translator as translator_module

        locales_dir = tmp_path / "locales"
        locales_dir.mkdir()
        (locales_dir / "fr.json").write_text(
            json.dumps({"greeting": "Bonjour {name} !"}, ensure_ascii=False),
            encoding="utf-8",
        )

        monkeypatch.setattr(translator_module, "_LOCALES_DIR", locales_dir)
        _translations_cache.clear()

        result = get_text("greeting", "fr", name="Alice")
        assert result == "Bonjour Alice !"

    def test_substitutes_multiple_kwargs(self, tmp_path, monkeypatch):
        import json
        from src.i18n import translator as translator_module

        locales_dir = tmp_path / "locales"
        locales_dir.mkdir()
        (locales_dir / "fr.json").write_text(
            json.dumps({"msg": "{count} erreurs dans {file}."}, ensure_ascii=False),
            encoding="utf-8",
        )

        monkeypatch.setattr(translator_module, "_LOCALES_DIR", locales_dir)
        _translations_cache.clear()

        result = get_text("msg", "fr", count=3, file="app.py")
        assert result == "3 erreurs dans app.py."

    def test_missing_kwarg_returns_unformatted_template(self, tmp_path, monkeypatch):
        """If a required kwarg is absent, the raw template string is returned (no crash)."""
        import json
        from src.i18n import translator as translator_module

        locales_dir = tmp_path / "locales"
        locales_dir.mkdir()
        (locales_dir / "fr.json").write_text(
            json.dumps({"msg": "Bonjour {name} !"}, ensure_ascii=False),
            encoding="utf-8",
        )

        monkeypatch.setattr(translator_module, "_LOCALES_DIR", locales_dir)
        _translations_cache.clear()

        # Missing `name` kwarg — should not raise, returns original template
        result = get_text("msg", "fr")
        assert result == "Bonjour {name} !"

    def test_extra_kwargs_are_ignored(self, tmp_path, monkeypatch):
        """Extra kwargs beyond what the template uses do not cause errors."""
        import json
        from src.i18n import translator as translator_module

        locales_dir = tmp_path / "locales"
        locales_dir.mkdir()
        (locales_dir / "fr.json").write_text(
            json.dumps({"msg": "Bonjour {name} !"}, ensure_ascii=False),
            encoding="utf-8",
        )

        monkeypatch.setattr(translator_module, "_LOCALES_DIR", locales_dir)
        _translations_cache.clear()

        result = get_text("msg", "fr", name="Bob", extra="ignored")
        assert result == "Bonjour Bob !"


# ---------------------------------------------------------------------------
# get_text() — missing key behaviour
# ---------------------------------------------------------------------------


class TestGetTextMissingKey:
    def test_missing_top_level_key_returns_key(self):
        result = get_text("nonexistent_key_xyz", "fr")
        assert result == "nonexistent_key_xyz"

    def test_missing_nested_key_returns_full_dotted_key(self):
        result = get_text("errors.nonexistent_sub_key", "fr")
        assert result == "errors.nonexistent_sub_key"

    def test_missing_deeply_nested_key_returns_full_dotted_key(self):
        result = get_text("a.b.c.d", "fr")
        assert result == "a.b.c.d"

    def test_missing_key_in_en_falls_back_to_fr_then_returns_key(self):
        """When key is absent in 'en' and also in 'fr', the key itself is returned."""
        result = get_text("totally_unknown_key", "en")
        assert result == "totally_unknown_key"

    def test_returns_string_not_none(self):
        result = get_text("nonexistent_key_xyz", "fr")
        assert result is not None
        assert isinstance(result, str)

    def test_partial_path_that_points_to_dict_returns_key(self):
        """Requesting a key that resolves to a dict (not a string) returns the key."""
        result = get_text("errors", "fr")
        assert result == "errors"

    def test_partial_path_nested_dict_returns_key(self):
        result = get_text("chat", "en")
        assert result == "chat"


# ---------------------------------------------------------------------------
# get_text() — invalid / unsupported locale fallback
# ---------------------------------------------------------------------------


class TestGetTextInvalidLocale:
    def test_unsupported_locale_string_falls_back_to_fr(self):
        result = get_text("welcome", "de")  # type: ignore[arg-type]
        # Should fall back to DEFAULT_LOCALE ("fr")
        assert result == "Bienvenue sur l'API ChatVote"

    def test_empty_string_locale_falls_back_to_fr(self):
        result = get_text("welcome", "")  # type: ignore[arg-type]
        assert result == "Bienvenue sur l'API ChatVote"

    def test_uppercase_locale_falls_back_to_fr(self):
        """'FR' is not in SUPPORTED_LOCALES (case-sensitive), so falls back to 'fr'."""
        result = get_text("welcome", "FR")  # type: ignore[arg-type]
        assert result == "Bienvenue sur l'API ChatVote"

    def test_locale_with_region_suffix_falls_back_to_fr(self):
        """'en-US' is not in SUPPORTED_LOCALES, so falls back to 'fr'."""
        result = get_text("welcome", "en-US")  # type: ignore[arg-type]
        assert result == "Bienvenue sur l'API ChatVote"

    def test_none_like_invalid_locale_falls_back_to_fr(self):
        result = get_text("welcome", "xx")  # type: ignore[arg-type]
        assert result == "Bienvenue sur l'API ChatVote"


# ---------------------------------------------------------------------------
# _load_translations() — caching behaviour
# ---------------------------------------------------------------------------


class TestLoadTranslationsCache:
    def test_second_call_returns_same_object(self):
        """_load_translations() must return the cached dict on second call (identity check)."""
        first = _load_translations("fr")
        second = _load_translations("fr")
        assert first is second

    def test_cache_populated_after_first_call(self):
        assert "fr" not in _translations_cache
        _load_translations("fr")
        assert "fr" in _translations_cache

    def test_cache_cleared_by_clear_cache(self):
        _load_translations("fr")
        _load_translations("en")
        assert "fr" in _translations_cache
        assert "en" in _translations_cache
        clear_cache()
        assert len(_translations_cache) == 0

    def test_fr_and_en_cached_independently(self):
        fr_data = _load_translations("fr")
        en_data = _load_translations("en")
        assert "fr" in _translations_cache
        assert "en" in _translations_cache
        assert fr_data is not en_data

    def test_cache_miss_loads_from_disk(self):
        """After clearing the cache, the next call reads from disk and repopulates."""
        _load_translations("fr")
        clear_cache()
        assert "fr" not in _translations_cache
        result = _load_translations("fr")
        assert "fr" in _translations_cache
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_get_text_call_populates_cache(self):
        assert "en" not in _translations_cache
        get_text("welcome", "en")
        assert "en" in _translations_cache

    def test_cached_dict_is_not_mutated_between_calls(self):
        first = _load_translations("fr")
        original_keys = set(first.keys())
        _load_translations("fr")
        assert set(first.keys()) == original_keys


# ---------------------------------------------------------------------------
# Translation file structure — top-level keys
# ---------------------------------------------------------------------------


class TestTranslationFileStructure:
    EXPECTED_TOP_LEVEL_KEYS = {"welcome", "errors", "chat", "rag", "voting_behavior", "prompts"}

    def test_fr_has_all_expected_top_level_keys(self):
        translations = _load_translations("fr")
        assert self.EXPECTED_TOP_LEVEL_KEYS.issubset(set(translations.keys()))

    def test_en_has_all_expected_top_level_keys(self):
        translations = _load_translations("en")
        assert self.EXPECTED_TOP_LEVEL_KEYS.issubset(set(translations.keys()))

    def test_fr_and_en_have_same_top_level_keys(self):
        fr = _load_translations("fr")
        en = _load_translations("en")
        assert set(fr.keys()) == set(en.keys())

    def test_errors_section_has_expected_sub_keys(self):
        expected = {
            "generic",
            "cannot_answer",
            "session_not_started",
            "timeout_party_documents",
            "timeout_party_responses",
            "validation_error",
        }
        for locale in ("fr", "en"):
            translations = _load_translations(locale)
            assert expected.issubset(set(translations["errors"].keys())), (
                f"locale '{locale}' errors section missing keys"
            )

    def test_chat_section_has_expected_sub_keys(self):
        expected = {"summary_placeholder", "no_title", "default_title"}
        for locale in ("fr", "en"):
            translations = _load_translations(locale)
            assert expected.issubset(set(translations["chat"].keys())), (
                f"locale '{locale}' chat section missing keys"
            )

    def test_rag_section_has_expected_sub_keys(self):
        expected = {"no_info_found", "no_candidate_info", "no_manifesto_info"}
        for locale in ("fr", "en"):
            translations = _load_translations(locale)
            assert expected.issubset(set(translations["rag"].keys())), (
                f"locale '{locale}' rag section missing keys"
            )

    def test_voting_behavior_section_has_expected_sub_keys(self):
        expected = {"no_votes_found", "cannot_provide_info"}
        for locale in ("fr", "en"):
            translations = _load_translations(locale)
            assert expected.issubset(set(translations["voting_behavior"].keys())), (
                f"locale '{locale}' voting_behavior section missing keys"
            )

    def test_prompts_section_has_expected_sub_keys(self):
        expected = {"response_language", "use_simple_language"}
        for locale in ("fr", "en"):
            translations = _load_translations(locale)
            assert expected.issubset(set(translations["prompts"].keys())), (
                f"locale '{locale}' prompts section missing keys"
            )


# ---------------------------------------------------------------------------
# Translation file values — all leaf values are strings
# ---------------------------------------------------------------------------


class TestTranslationFileValues:
    def _collect_leaf_values(self, data: dict, path: str = "") -> list[tuple[str, object]]:
        """Recursively collect all leaf (non-dict) values with their dotted path."""
        results = []
        for k, v in data.items():
            full_path = f"{path}.{k}" if path else k
            if isinstance(v, dict):
                results.extend(self._collect_leaf_values(v, full_path))
            else:
                results.append((full_path, v))
        return results

    def test_all_fr_leaf_values_are_strings(self):
        translations = _load_translations("fr")
        leaf_values = self._collect_leaf_values(translations)
        assert len(leaf_values) > 0, "fr.json has no leaf values"
        non_strings = [(k, v) for k, v in leaf_values if not isinstance(v, str)]
        assert non_strings == [], (
            f"Non-string leaf values in fr.json: {non_strings}"
        )

    def test_all_en_leaf_values_are_strings(self):
        translations = _load_translations("en")
        leaf_values = self._collect_leaf_values(translations)
        assert len(leaf_values) > 0, "en.json has no leaf values"
        non_strings = [(k, v) for k, v in leaf_values if not isinstance(v, str)]
        assert non_strings == [], (
            f"Non-string leaf values in en.json: {non_strings}"
        )

    def test_no_null_values_in_fr(self):
        translations = _load_translations("fr")
        leaf_values = self._collect_leaf_values(translations)
        null_entries = [(k, v) for k, v in leaf_values if v is None]
        assert null_entries == [], f"Null values in fr.json: {null_entries}"

    def test_no_null_values_in_en(self):
        translations = _load_translations("en")
        leaf_values = self._collect_leaf_values(translations)
        null_entries = [(k, v) for k, v in leaf_values if v is None]
        assert null_entries == [], f"Null values in en.json: {null_entries}"

    def test_no_empty_strings_in_fr(self):
        translations = _load_translations("fr")
        leaf_values = self._collect_leaf_values(translations)
        empty_entries = [(k, v) for k, v in leaf_values if v == ""]
        assert empty_entries == [], f"Empty string values in fr.json: {empty_entries}"

    def test_no_empty_strings_in_en(self):
        translations = _load_translations("en")
        leaf_values = self._collect_leaf_values(translations)
        empty_entries = [(k, v) for k, v in leaf_values if v == ""]
        assert empty_entries == [], f"Empty string values in en.json: {empty_entries}"

    def test_fr_and_en_have_same_number_of_leaf_values(self):
        fr_translations = _load_translations("fr")
        en_translations = _load_translations("en")
        fr_leaves = self._collect_leaf_values(fr_translations)
        en_leaves = self._collect_leaf_values(en_translations)
        assert len(fr_leaves) == len(en_leaves), (
            f"fr.json has {len(fr_leaves)} leaf values, en.json has {len(en_leaves)}"
        )

    def test_fr_and_en_have_same_leaf_key_paths(self):
        """Both locale files expose the exact same set of dotted key paths."""
        fr_translations = _load_translations("fr")
        en_translations = _load_translations("en")
        fr_paths = {k for k, _ in self._collect_leaf_values(fr_translations)}
        en_paths = {k for k, _ in self._collect_leaf_values(en_translations)}
        assert fr_paths == en_paths, (
            f"Key path mismatch — only in fr: {fr_paths - en_paths}, "
            f"only in en: {en_paths - fr_paths}"
        )


# ---------------------------------------------------------------------------
# Helper functions — get_supported_locales / is_valid_locale / normalize_locale
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    def test_get_supported_locales_returns_fr_and_en(self):
        locales = get_supported_locales()
        assert "fr" in locales
        assert "en" in locales

    def test_get_supported_locales_returns_tuple(self):
        assert isinstance(get_supported_locales(), tuple)

    def test_is_valid_locale_true_for_fr(self):
        assert is_valid_locale("fr") is True

    def test_is_valid_locale_true_for_en(self):
        assert is_valid_locale("en") is True

    def test_is_valid_locale_false_for_unknown(self):
        assert is_valid_locale("de") is False

    def test_is_valid_locale_false_for_uppercase(self):
        assert is_valid_locale("FR") is False

    def test_is_valid_locale_false_for_empty_string(self):
        assert is_valid_locale("") is False

    def test_normalize_locale_fr_unchanged(self):
        assert normalize_locale("fr") == "fr"

    def test_normalize_locale_en_unchanged(self):
        assert normalize_locale("en") == "en"

    def test_normalize_locale_uppercase_fr(self):
        assert normalize_locale("FR") == "fr"

    def test_normalize_locale_uppercase_en(self):
        assert normalize_locale("EN") == "en"

    def test_normalize_locale_en_us_region_suffix(self):
        assert normalize_locale("en-US") == "en"

    def test_normalize_locale_fr_fr_region_suffix(self):
        assert normalize_locale("fr-FR") == "fr"

    def test_normalize_locale_en_underscore_variant(self):
        assert normalize_locale("en_US") == "en"

    def test_normalize_locale_none_returns_default(self):
        assert normalize_locale(None) == DEFAULT_LOCALE

    def test_normalize_locale_unknown_returns_default(self):
        assert normalize_locale("de") == DEFAULT_LOCALE

    def test_normalize_locale_empty_string_returns_default(self):
        assert normalize_locale("") == DEFAULT_LOCALE

    def test_supported_locales_constant_contains_fr_and_en(self):
        assert "fr" in SUPPORTED_LOCALES
        assert "en" in SUPPORTED_LOCALES
