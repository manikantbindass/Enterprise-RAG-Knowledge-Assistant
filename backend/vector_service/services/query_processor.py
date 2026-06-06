"""
Query preprocessing: normalization, abbreviation expansion, entity extraction.
Clean/expand the raw query before embedding or BM25 search.
"""

from __future__ import annotations

import re
import unicodedata

import structlog

logger = structlog.get_logger(__name__)

# Common enterprise abbreviations → full form
_ABBREVIATIONS: dict[str, str] = {
    "hr": "human resources",
    "it": "information technology",
    "cto": "chief technology officer",
    "ceo": "chief executive officer",
    "cfo": "chief financial officer",
    "sla": "service level agreement",
    "kpi": "key performance indicator",
    "roi": "return on investment",
    "erp": "enterprise resource planning",
    "crm": "customer relationship management",
    "api": "application programming interface",
    "ui": "user interface",
    "ux": "user experience",
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "nlp": "natural language processing",
    "rag": "retrieval augmented generation",
    "llm": "large language model",
    "pii": "personally identifiable information",
    "gdpr": "general data protection regulation",
    "hipaa": "health insurance portability and accountability act",
    "soc": "security operations center",
    "mfa": "multi-factor authentication",
    "sso": "single sign-on",
    "vpn": "virtual private network",
    "infra": "infrastructure",
    "k8s": "kubernetes",
    "ci": "continuous integration",
    "cd": "continuous deployment",
    "qa": "quality assurance",
    "po": "purchase order",
    "ap": "accounts payable",
    "ar": "accounts receivable",
    "p&l": "profit and loss",
}

# Patterns that hint at metadata intent
_DATE_PATTERN = re.compile(
    r"\b(\d{4}[-/]\d{2}[-/]\d{2}|"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+\d{1,2}(?:,\s*\d{4})?)\b",
    re.IGNORECASE,
)
_DEPT_PATTERN = re.compile(
    r"\b(engineering|finance|legal|compliance|hr|sales|marketing|"
    r"operations|product|design|security|devops|infrastructure)\s+(?:team|department|dept)?\b",
    re.IGNORECASE,
)


class ProcessedQuery:
    """Container for preprocessed query data."""

    __slots__ = (
        "original",
        "normalized",
        "expanded",
        "detected_departments",
        "detected_date_hints",
        "is_question",
    )

    def __init__(
        self,
        original: str,
        normalized: str,
        expanded: str,
        detected_departments: list[str],
        detected_date_hints: list[str],
        is_question: bool,
    ) -> None:
        self.original = original
        self.normalized = normalized
        self.expanded = expanded
        self.detected_departments = detected_departments
        self.detected_date_hints = detected_date_hints
        self.is_question = is_question


class QueryProcessor:
    """
    Stateless query preprocessor.
    All methods are pure functions — no I/O, no side effects.
    """

    def process(self, query: str) -> ProcessedQuery:
        """Full preprocessing pipeline."""
        normalized = self._normalize(query)
        expanded = self._expand_abbreviations(normalized)
        departments = self._extract_departments(normalized)
        date_hints = self._extract_date_hints(normalized)
        is_q = self._is_question(normalized)

        logger.debug(
            "query_processed",
            original=query[:80],
            expanded=expanded[:80],
            departments=departments,
            is_question=is_q,
        )
        return ProcessedQuery(
            original=query,
            normalized=normalized,
            expanded=expanded,
            detected_departments=departments,
            detected_date_hints=date_hints,
            is_question=is_q,
        )

    # ── Private ────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize(text: str) -> str:
        """
        Unicode normalization → lower case → collapse whitespace.
        Strips zero-width chars, smart quotes, etc.
        """
        # NFC normalization
        text = unicodedata.normalize("NFC", text)
        # Replace smart quotes
        text = text.replace("\u2018", "'").replace("\u2019", "'")
        text = text.replace("\u201c", '"').replace("\u201d", '"')
        # Strip zero-width chars
        text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
        # Collapse internal whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _expand_abbreviations(text: str) -> str:
        """
        Word-boundary-safe abbreviation expansion.
        Preserves original casing context for readability.
        """
        words = text.split()
        expanded: list[str] = []
        for word in words:
            key = word.lower().rstrip(".,;:?!")
            if key in _ABBREVIATIONS:
                expansion = _ABBREVIATIONS[key]
                # Append punctuation back if stripped
                suffix = word[len(key):]
                expanded.append(expansion + suffix)
            else:
                expanded.append(word)
        return " ".join(expanded)

    @staticmethod
    def _extract_departments(text: str) -> list[str]:
        """Extract department mentions for metadata filter hints."""
        matches = _DEPT_PATTERN.findall(text)
        return list({m.lower() for m in matches})

    @staticmethod
    def _extract_date_hints(text: str) -> list[str]:
        """Extract date-like strings for metadata filter hints."""
        return [m.group(0) for m in _DATE_PATTERN.finditer(text)]

    @staticmethod
    def _is_question(text: str) -> bool:
        """Detect interrogative structure for intent hints."""
        question_words = ("what", "who", "where", "when", "why", "how", "which", "whose")
        lower = text.lower().strip()
        return lower.endswith("?") or lower.split()[0] in question_words if lower else False
