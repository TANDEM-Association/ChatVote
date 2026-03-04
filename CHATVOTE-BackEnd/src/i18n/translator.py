# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Translation utilities for ChatVote backend internationalization.

Provides functions to retrieve translated strings based on locale.
"""

import json
import logging
from pathlib import Path
from typing import Literal, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Type alias for supported locales
Locale = Literal["fr", "en"]

# Default locale (French)
DEFAULT_LOCALE: Locale = "fr"

# Supported locales
SUPPORTED_LOCALES: tuple[Locale, ...] = ("fr", "en")

# Cache for loaded translations
_translations_cache: Dict[Locale, Dict[str, Any]] = {}

# Path to locale files
_LOCALES_DIR = Path(__file__).parent / "locales"


def _load_translations(locale: Locale) -> Dict[str, Any]:
    """
    Load translations from JSON file for the given locale.

    Args:
        locale: The locale to load translations for.

    Returns:
        Dictionary containing all translations for the locale.
    """
    if locale in _translations_cache:
        return _translations_cache[locale]

    locale_file = _LOCALES_DIR / f"{locale}.json"

    if not locale_file.exists():
        logger.warning(
            f"Locale file not found: {locale_file}, falling back to {DEFAULT_LOCALE}"
        )
        locale_file = _LOCALES_DIR / f"{DEFAULT_LOCALE}.json"

    try:
        with open(locale_file, "r", encoding="utf-8") as f:
            translations = json.load(f)
            _translations_cache[locale] = translations
            return translations
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error loading translations for {locale}: {e}")
        return {}


def get_text(key: str, locale: Locale = DEFAULT_LOCALE, **kwargs: Any) -> str:
    """
    Get a translated text string for the given key and locale.

    Args:
        key: The translation key (e.g., "error_generic", "welcome").
        locale: The locale to use for translation.
        **kwargs: Optional format arguments to interpolate into the string.

    Returns:
        The translated string, or the key itself if not found.

    Example:
        >>> get_text("welcome", "en")
        "Welcome to the ChatVote API"
        >>> get_text("error_with_param", "fr", param="test")
        "Erreur avec test"
    """
    if locale not in SUPPORTED_LOCALES:
        logger.warning(
            f"Unsupported locale '{locale}', falling back to {DEFAULT_LOCALE}"
        )
        locale = DEFAULT_LOCALE

    translations = _load_translations(locale)

    # Support nested keys with dot notation (e.g., "errors.generic")
    keys = key.split(".")
    value: Any = translations

    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            value = None
            break

    if value is None:
        logger.warning(f"Translation key '{key}' not found for locale '{locale}'")
        # Try fallback to default locale
        if locale != DEFAULT_LOCALE:
            return get_text(key, DEFAULT_LOCALE, **kwargs)
        return key

    if not isinstance(value, str):
        logger.warning(f"Translation value for '{key}' is not a string")
        return key

    # Apply format arguments if provided
    if kwargs:
        try:
            value = value.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing format argument {e} for translation key '{key}'")

    return value


def get_supported_locales() -> tuple[Locale, ...]:
    """
    Get the tuple of supported locales.

    Returns:
        Tuple of supported locale codes.
    """
    return SUPPORTED_LOCALES


def is_valid_locale(locale: str) -> bool:
    """
    Check if a locale string is valid/supported.

    Args:
        locale: The locale string to check.

    Returns:
        True if the locale is supported, False otherwise.
    """
    return locale in SUPPORTED_LOCALES


def normalize_locale(locale: Optional[str]) -> Locale:
    """
    Normalize a locale string to a supported locale.

    Handles common variations like "en-US", "en_US", "EN", etc.

    Args:
        locale: The locale string to normalize (can be None).

    Returns:
        A valid Locale, defaulting to DEFAULT_LOCALE if invalid.
    """
    if locale is None:
        return DEFAULT_LOCALE

    # Normalize: lowercase, take first part before - or _
    normalized = locale.lower().split("-")[0].split("_")[0]

    if normalized in SUPPORTED_LOCALES:
        return normalized  # type: ignore

    return DEFAULT_LOCALE


def clear_cache() -> None:
    """
    Clear the translations cache.

    Useful for testing or when locale files are updated at runtime.
    """
    _translations_cache.clear()
