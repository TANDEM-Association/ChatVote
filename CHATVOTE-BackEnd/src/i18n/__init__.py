# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Internationalization (i18n) module for ChatVote backend.

Supports French (default) and English locales.
"""

from src.i18n.translator import (
    Locale,
    DEFAULT_LOCALE,
    get_text,
    get_supported_locales,
    is_valid_locale,
    normalize_locale,
)

__all__ = [
    "Locale",
    "DEFAULT_LOCALE",
    "get_text",
    "get_supported_locales",
    "is_valid_locale",
    "normalize_locale",
]
