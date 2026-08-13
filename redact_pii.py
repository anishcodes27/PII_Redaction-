"""
PII Redaction Tool – Main Orchestrator.

Reads a .docx file, detects all PII entities using the HybridDetector,
replaces them with Faker-generated synthetic data via FakerReplacer,
and writes the redacted document to a new .docx file.

Usage:
    python redact_pii.py --input "data/Red Herring Prospectus.docx" \\
                         --output "output/Redacted_Red_Herring_Prospectus.docx"
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

from docx import Document

from config import ENTITY_TYPES
from docx_handler import DocxReader, DocxWriter
from pii_detector import HybridDetector, PIISpan
from pii_replacer import FakerReplacer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("redact_pii")


def build_replacement_pairs(
    segments_text: List[str],
    detector: HybridDetector,
    replacer: FakerReplacer,
) -> Tuple[List[Tuple[str, str]], Dict[str, int], List[dict]]:
    """
    Detect PII across all text segments and build replacement pairs.

    Returns:
        replacements: Deduplicated list of (original, fake) string tuples.
        entity_counts: Dict mapping entity type to detection count.
        predictions: List of detection dicts for evaluation export.
    """
    seen_originals: Dict[str, str] = {}
    entity_counts: Dict[str, int] = defaultdict(int)
    predictions: List[dict] = []

    for segment_idx, text in enumerate(segments_text):
        spans: List[PIISpan] = detector.detect(text)
        for span in spans:
            original = span.text.strip()
            if not original:
                continue
            if original not in seen_originals:
                fake = replacer.replace(span.entity_type, original)
                seen_originals[original] = fake
            entity_counts[span.entity_type] += 1
            predictions.append(
                {
                    "segment_index": segment_idx,
                    "start": span.start,
                    "end": span.end,
                    "entity_type": span.entity_type,
                    "text": original,
                    "score": span.score,
                    "source": span.source,
                }
            )

    replacements = list(seen_originals.items())
    return replacements, dict(entity_counts), predictions


def print_summary(entity_counts: Dict[str, int]) -> None:
    """Print a formatted detection summary to stdout."""
    total = sum(entity_counts.values())
    logger.info("=" * 60)
    logger.info("DETECTION SUMMARY")
    logger.info("=" * 60)
    for entity_type in sorted(entity_counts):
        logger.info("  %-20s : %d", entity_type, entity_counts[entity_type])
    logger.info("-" * 60)
    logger.info("  %-20s : %d", "TOTAL", total)
    logger.info("=" * 60)


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    """Define and parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Redact PII from a .docx file using a Hybrid Regex + NER pipeline.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/Red Herring Prospectus.docx"),
        help="Path to the input .docx file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/Redacted_Red_Herring_Prospectus.docx"),
        help="Path for the redacted output .docx file.",
    )
    parser.add_argument(
        "--predictions-out",
        type=Path,
        default=Path("output/predictions.json"),
        help="Path to save the predictions JSON for evaluation.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity level.",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> None:
    """Entry point: orchestrate detection, replacement, and document saving."""
    args = parse_args(argv)

    logging.getLogger().setLevel(getattr(logging, args.log_level))

    if not args.input.exists():
        logger.error("Input file not found: %s", args.input)
        sys.exit(1)

    logger.info("Loading document: %s", args.input)
    reader = DocxReader(args.input)
    segments = reader.extract_segments()
    segment_texts = [seg.text for seg in segments]

    logger.info("Initialising detection pipeline …")
    detector = HybridDetector()
    replacer = FakerReplacer()

    logger.info("Running PII detection across %d text segments …", len(segment_texts))
    replacements, entity_counts, predictions = build_replacement_pairs(
        segment_texts, detector, replacer
    )

    print_summary(entity_counts)
    logger.info("Total unique PII values to replace: %d", len(replacements))

    logger.info("Applying replacements to document …")
    writer = DocxWriter(reader.document)
    writer.apply_replacements(replacements)
    writer.save(args.output)

    args.predictions_out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.predictions_out, "w", encoding="utf-8") as fh:
        json.dump(predictions, fh, indent=2, ensure_ascii=False)
    logger.info("Predictions saved to: %s", args.predictions_out)

    logger.info("Redaction complete. Output: %s", args.output)


if __name__ == "__main__":
    main()
