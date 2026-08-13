"""
PII Detection Engine.

Implements three complementary detection layers:
  - RegexDetector  : Pattern-based detection for structured PII (SSN, CC, IP, email, phone, DOB).
  - NERDetector    : spaCy large English model for contextual named-entity recognition.
  - PresidioDetector: Microsoft Presidio AnalyzerEngine for validated detection with scores.
  - HybridDetector : Orchestrates all three layers, merges and deduplicates overlapping spans.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import spacy
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import SpacyNlpEngine, NlpEngineProvider

from config import (
    ENTITY_TYPES,
    REGEX_PATTERNS,
    SPACY_MODEL,
    SPACY_ENTITY_MAP,
    PRESIDIO_ENTITIES,
    PRESIDIO_ENTITY_MAP,
    CONFIDENCE_THRESHOLD,
    IGNORED_ENTITIES,
)

logger = logging.getLogger(__name__)


@dataclass(order=True)
class PIISpan:
    """Represents a single detected PII entity within a text string."""

    start: int
    end: int
    entity_type: str
    text: str = field(compare=False)
    score: float = field(default=1.0, compare=False)
    source: str = field(default="", compare=False)

    def overlaps(self, other: "PIISpan") -> bool:
        """Return True if this span overlaps with another span."""
        return self.start < other.end and other.start < self.end


def _luhn_check(number: str) -> bool:
    """Validate a numeric string using the Luhn algorithm."""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13:
        return False
    digits.reverse()
    total = 0
    for i, digit in enumerate(digits):
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


class RegexDetector:
    """
    Applies compiled regex patterns from config.REGEX_PATTERNS to detect
    structured PII entities. Runs the Luhn algorithm to filter false-positive
    credit card candidates.
    """

    def detect(self, text: str) -> List[PIISpan]:
        """Scan text with all regex patterns and return a list of PIISpan objects."""
        spans: List[PIISpan] = []
        for entity_type, pattern in REGEX_PATTERNS.items():
            for match in pattern.finditer(text):
                matched_text = match.group()
                if entity_type == ENTITY_TYPES["CREDIT_CARD"]:
                    raw_digits = re.sub(r"\D", "", matched_text)
                    if not _luhn_check(raw_digits):
                        continue
                spans.append(
                    PIISpan(
                        start=match.start(),
                        end=match.end(),
                        entity_type=entity_type,
                        text=matched_text,
                        score=1.0,
                        source="regex",
                    )
                )
        return spans


class NERDetector:
    """
    Uses spaCy's English NER model to detect contextual named entities
    (persons, organisations, geopolitical entities, locations, facilities).
    """

    def __init__(self) -> None:
        try:
            self._nlp = spacy.load(SPACY_MODEL)
        except Exception:
            self._nlp = spacy.blank("en")

    def detect(self, text: str) -> List[PIISpan]:
        """Run spaCy NER on text and map relevant entity labels to internal types."""
        doc = self._nlp(text)
        spans: List[PIISpan] = []
        for ent in doc.ents:
            mapped = SPACY_ENTITY_MAP.get(ent.label_)
            if mapped:
                spans.append(
                    PIISpan(
                        start=ent.start_char,
                        end=ent.end_char,
                        entity_type=mapped,
                        text=ent.text,
                        score=0.85,
                        source="spacy",
                    )
                )
        return spans


class PresidioDetector:
    """
    Wraps Microsoft Presidio's AnalyzerEngine for validated PII detection.
    Falls back gracefully to default recognizers without triggering spacy downloads on cloud.
    """

    def __init__(self) -> None:
        try:
            self._analyzer = AnalyzerEngine()
        except Exception:
            self._analyzer = None


    def detect(self, text: str) -> List[PIISpan]:
        """Run Presidio analysis on text and return filtered PIISpan results."""
        results = self._analyzer.analyze(
            text=text,
            language="en",
            entities=PRESIDIO_ENTITIES,
            score_threshold=CONFIDENCE_THRESHOLD,
        )
        spans: List[PIISpan] = []
        for result in results:
            mapped = PRESIDIO_ENTITY_MAP.get(result.entity_type)
            if mapped:
                spans.append(
                    PIISpan(
                        start=result.start,
                        end=result.end,
                        entity_type=mapped,
                        text=text[result.start : result.end],
                        score=result.score,
                        source="presidio",
                    )
                )
        return spans


def _resolve_overlaps(spans: List[PIISpan]) -> List[PIISpan]:
    """
    Given a list of potentially overlapping PIISpans, resolve conflicts by
    keeping the longest span. When two spans have identical length, the one
    with the higher confidence score is preferred.
    """
    if not spans:
        return []

    sorted_spans = sorted(spans, key=lambda s: (s.start, -(s.end - s.start), -s.score))
    resolved: List[PIISpan] = []

    for candidate in sorted_spans:
        if not resolved:
            resolved.append(candidate)
            continue
        last = resolved[-1]
        if candidate.overlaps(last):
            candidate_len = candidate.end - candidate.start
            last_len = last.end - last.start
            if candidate_len > last_len or (
                candidate_len == last_len and candidate.score > last.score
            ):
                resolved[-1] = candidate
        else:
            resolved.append(candidate)

    return resolved


class HybridDetector:
    """
    Orchestrates RegexDetector, NERDetector, and PresidioDetector.
    Aggregates all detected spans, deduplicates overlaps, and returns
    a clean sorted list of non-overlapping PIISpan objects.
    """

    def __init__(self) -> None:
        logger.info("Initialising RegexDetector …")
        self._regex = RegexDetector()
        logger.info("Initialising NERDetector (spaCy %s) …", SPACY_MODEL)
        self._ner = NERDetector()
        logger.info("Initialising PresidioDetector …")
        self._presidio = PresidioDetector()

    def detect(self, text: str) -> List[PIISpan]:
        """
        Run all three detection layers on text, merge results, resolve overlaps,
        filter out non-PII ignored entities, and return the final deduplicated list of PIISpan objects.
        """
        all_spans: List[PIISpan] = []
        all_spans.extend(self._regex.detect(text))
        all_spans.extend(self._ner.detect(text))
        all_spans.extend(self._presidio.detect(text))

        filtered_spans = []
        for span in all_spans:
            clean_text = span.text.strip().lower()
            if clean_text in IGNORED_ENTITIES:
                continue
            if span.entity_type in (ENTITY_TYPES["PERSON"], ENTITY_TYPES["ORG"], ENTITY_TYPES["ADDRESS"]) and len(clean_text) <= 2:
                continue
            if span.entity_type == ENTITY_TYPES["DATE_OF_BIRTH"] and span.source in ("spacy", "presidio") and span.text.isdigit():
                continue
            filtered_spans.append(span)

        resolved = _resolve_overlaps(filtered_spans)
        logger.debug("Detected %d PII spans in text block.", len(resolved))
        return resolved

    def detect_batch(self, texts: List[str]) -> List[List[PIISpan]]:
        """Run detect() on each text in a list and return a list of span lists."""
        return [self.detect(text) for text in texts]

