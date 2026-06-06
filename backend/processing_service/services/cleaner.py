"""
Text cleaning service.

Removes noise from extracted text:
  - null bytes and control characters
  - normalize whitespace
  - fix common encoding artifacts
  - strip boilerplate headers/footers (heuristic)
  - handle special characters
"""

from __future__ import annotations

import re
import unicodedata

import structlog

logger = structlog.get_logger(__name__)

# Patterns for boilerplate detection
_HEADER_FOOTER_PATTERNS = [
    re.compile(r"^\s*page\s+\d+\s+of\s+\d+\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*confidential\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*proprietary\s+and\s+confidential\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*all\s+rights\s+reserved\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*copyright\s+©?\s*\d{4}\s*.*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*\d+\s*$", re.MULTILINE),  # Lone page numbers
]

# Common encoding artifacts
_ENCODING_FIXES: list[tuple[str, str]] = [
    ("\u2019", "'"),   # curly apostrophe
    ("\u2018", "'"),   # curly apostrophe (open)
    ("\u201c", '"'),   # curly quote (open)
    ("\u201d", '"'),   # curly quote (close)
    ("\u2013", "-"),   # en dash
    ("\u2014", "--"),  # em dash
    ("\u00a0", " "),   # non-breaking space
    ("\u200b", ""),    # zero-width space
    ("\u00ad", ""),    # soft hyphen
    ("\ufeff", ""),    # BOM
    ("\u2022", "-"),   # bullet
    ("\u2026", "..."), # ellipsis
]

# Hyphenation artifact: word broken at line end
_HYPHENATION_RE = re.compile(r"(\w)-\n(\w)")


class TextCleaner:
    """
    Stateless text cleaning pipeline.

    All methods are pure functions — no side effects.
    Call clean() for the full pipeline.
    """

    def clean(self, text: str) -> str:
        """
        Apply full cleaning pipeline.

        Order matters:
        1. Normalize unicode
        2. Fix encoding artifacts
        3. Remove null bytes / control chars
        4. Fix hyphenation
        5. Strip boilerplate lines
        6. Normalize whitespace
        """
        if not text:
            return ""

        text = self._normalize_unicode(text)
        text = self._fix_encoding_artifacts(text)
        text = self._remove_control_characters(text)
        text = self._fix_hyphenation(text)
        text = self._remove_boilerplate(text)
        text = self._normalize_whitespace(text)
        return text.strip()

    def _normalize_unicode(self, text: str) -> str:
        """NFC normalize — ensures consistent representation."""
        try:
            return unicodedata.normalize("NFC", text)
        except (TypeError, ValueError):
            return text

    def _fix_encoding_artifacts(self, text: str) -> str:
        """Replace common mojibake / encoding artifacts."""
        for wrong, right in _ENCODING_FIXES:
            text = text.replace(wrong, right)
        # Fix Â artifacts from latin1→utf8 double-encode
        text = text.replace("Â ", " ").replace("Â\n", "\n")
        return text

    def _remove_control_characters(self, text: str) -> str:
        """
        Remove null bytes and non-printable control characters.

        Preserves: newlines (\n), tabs (\t), carriage return (\r)
        Removes: \x00-\x08, \x0b, \x0c, \x0e-\x1f, \x7f
        """
        # Remove null bytes first
        text = text.replace("\x00", "")
        # Remove other control chars (keep \t, \n, \r)
        return re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    def _fix_hyphenation(self, text: str) -> str:
        """
        Rejoin words split by soft hyphens at line breaks.

        Example: "informa-\ntion" → "information"
        """
        return _HYPHENATION_RE.sub(r"\1\2", text)

    def _remove_boilerplate(self, text: str) -> str:
        """
        Remove known boilerplate patterns (page numbers, copyright lines).

        Heuristic — may miss domain-specific boilerplate.
        """
        for pattern in _HEADER_FOOTER_PATTERNS:
            text = pattern.sub("", text)
        return text

    def _normalize_whitespace(self, text: str) -> str:
        """
        Collapse multiple spaces to one, normalize line endings.

        Preserves paragraph breaks (double newlines).
        """
        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # Collapse 3+ consecutive newlines to double newline (paragraph break)
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Collapse multiple spaces/tabs on a single line to single space
        text = re.sub(r"[ \t]{2,}", " ", text)
        # Remove trailing spaces on each line
        text = re.sub(r"[ \t]+\n", "\n", text)
        return text

    def clean_for_chunk(self, text: str) -> str:
        """
        Light cleaning suitable for individual chunks.

        Skips boilerplate removal (already done at document level).
        """
        if not text:
            return ""
        text = self._normalize_unicode(text)
        text = self._fix_encoding_artifacts(text)
        text = self._remove_control_characters(text)
        text = self._normalize_whitespace(text)
        return text.strip()

    def estimate_word_count(self, text: str) -> int:
        """Fast word count estimation."""
        return len(text.split())

    def estimate_char_count(self, text: str) -> int:
        """Character count excluding whitespace."""
        return len(text.replace(" ", "").replace("\n", "").replace("\t", ""))
