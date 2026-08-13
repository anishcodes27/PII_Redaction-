"""
Evaluation Script for the PII Redaction Tool.

Computes Precision, Recall, F1-Score, and Accuracy by comparing
model predictions against a ground-truth benchmark JSON file.

Evaluation is performed per entity type and in aggregate.

Usage:
    python evaluate.py \\
        --benchmark evaluation/benchmark.json \\
        --predictions output/predictions.json \\
        --report output/evaluation_report.md
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("evaluate")


@dataclass
class EntityRecord:
    """A normalised representation of a single PII detection or ground-truth annotation."""

    segment_index: int
    start: int
    end: int
    entity_type: str
    text: str

    def identity_key(self) -> Tuple[str, str]:
        """
        Return a normalised (entity_type, text) tuple used to match predictions
        against ground-truth. Text is lowercased and stripped for robust matching.
        """
        return (self.entity_type, self.text.strip().lower())


@dataclass
class MetricsResult:
    """Holds computed evaluation metrics for a single entity type or in aggregate."""

    entity_type: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    @property
    def precision(self) -> float:
        """TP / (TP + FP); returns 0.0 when there are no positive predictions."""
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 0.0

    @property
    def recall(self) -> float:
        """TP / (TP + FN); returns 0.0 when there are no actual positives."""
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else 0.0

    @property
    def f1(self) -> float:
        """Harmonic mean of Precision and Recall."""
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def accuracy(self) -> float:
        """
        Token-level accuracy approximation:
        TP / (TP + FP + FN).
        This represents how many detected entities are exactly correct
        relative to all unique entities considered.
        """
        denom = self.true_positives + self.false_positives + self.false_negatives
        return self.true_positives / denom if denom else 0.0


def load_records(path: Path) -> List[EntityRecord]:
    """
    Load EntityRecord objects from a JSON file.
    Expects a list of dicts with keys: segment_index, start, end, entity_type, text.
    Matching is **text-level** on `(entity_type, normalised_text)` — robust to offset differences between annotation passes.
    """
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    records = []
    for item in raw:
        records.append(
            EntityRecord(
                segment_index=int(item.get("segment_index", 0)),
                start=int(item["start"]),
                end=int(item["end"]),
                entity_type=str(item["entity_type"]),
                text=str(item.get("text", "")),
            )
        )
    return records


def compute_metrics(
    ground_truth: List[EntityRecord],
    predictions: List[EntityRecord],
) -> Dict[str, MetricsResult]:
    """
    Compare predictions against ground truth and compute per-entity-type metrics.

    Matching strategy: An entity is a True Positive when its (entity_type, normalised_text)
    pair appears in the ground-truth set. This text-level matching is robust to differences
    in segment indexing or character offsets between annotation passes.

    Returns:
        A dict mapping entity_type (and "AGGREGATE") to MetricsResult objects.
    """
    gt_keys: Set[Tuple] = {rec.identity_key() for rec in ground_truth}
    pred_keys: Set[Tuple] = {rec.identity_key() for rec in predictions}

    entity_types = sorted({rec.entity_type for rec in ground_truth + predictions})
    results: Dict[str, MetricsResult] = {et: MetricsResult(entity_type=et) for et in entity_types}
    results["AGGREGATE"] = MetricsResult(entity_type="AGGREGATE")

    counted_pred_keys: Set[Tuple] = set()
    for rec in predictions:
        et = rec.entity_type
        key = rec.identity_key()
        if key in gt_keys and key not in counted_pred_keys:
            results[et].true_positives += 1
            results["AGGREGATE"].true_positives += 1
            counted_pred_keys.add(key)
        elif key not in gt_keys:
            results[et].false_positives += 1
            results["AGGREGATE"].false_positives += 1

    for rec in ground_truth:
        et = rec.entity_type
        if rec.identity_key() not in pred_keys:
            results[et].false_negatives += 1
            results["AGGREGATE"].false_negatives += 1

    return results


def format_report(results: Dict[str, MetricsResult], benchmark_path: Path, predictions_path: Path) -> str:
    """
    Render a Markdown evaluation report from computed MetricsResult objects.
    """
    lines = [
        "# PII Redaction Tool — Evaluation Report",
        "",
        f"**Benchmark**: `{benchmark_path}`  ",
        f"**Predictions**: `{predictions_path}`",
        "",
        "---",
        "",
        "## Per-Entity-Type Metrics",
        "",
        "| Entity Type | Precision | Recall | F1-Score | Accuracy | TP | FP | FN |",
        "|---|---|---|---|---|---|---|---|",
    ]

    entity_types = sorted(k for k in results if k != "AGGREGATE")
    for et in entity_types:
        m = results[et]
        lines.append(
            f"| {et} | {m.precision:.3f} | {m.recall:.3f} | {m.f1:.3f} | {m.accuracy:.3f} "
            f"| {m.true_positives} | {m.false_positives} | {m.false_negatives} |"
        )

    agg = results.get("AGGREGATE")
    if agg:
        lines += [
            "|---|---|---|---|---|---|---|---|",
            f"| **AGGREGATE** | **{agg.precision:.3f}** | **{agg.recall:.3f}** "
            f"| **{agg.f1:.3f}** | **{agg.accuracy:.3f}** "
            f"| {agg.true_positives} | {agg.false_positives} | {agg.false_negatives} |",
        ]

    lines += [
        "",
        "---",
        "",
        "## Trade-Off Analysis",
        "",
        "### False Positives",
        "False positives arise primarily from:",
        "- Short common words matched by spaCy NER as PERSON or ORG (e.g., *Order*, *Table*).",
        "- Numeric sequences that pass regex patterns but are not actual credit cards or SSNs.",
        "- Overly broad DATE_TIME detections from Presidio that are not dates of birth.",
        "",
        "**Mitigation strategies applied:**",
        "- Luhn algorithm validation eliminates false credit-card positives.",
        "- SSN regex excludes invalid prefixes (000, 666, 9xx).",
        "- Confidence threshold of 0.4 on Presidio filters low-confidence hits.",
        "- Longest-span conflict resolution prevents partial duplicate matches.",
        "",
        "### False Negatives",
        "False negatives are most common in:",
        "- Non-standard phone formats (international numbers without country code).",
        "- Addresses embedded in dense paragraphs without clear delimiters.",
        "- Informal name references or abbreviations not recognised by spaCy.",
        "",
        "**Mitigation strategies applied:**",
        "- Three-layer hybrid pipeline: Regex + spaCy NER + Presidio maximises coverage.",
        "- spaCy `en_core_web_lg` provides the highest accuracy among off-the-shelf models.",
        "",
        "---",
        "",
        "## Recommendations",
        "",
        "1. Annotate more ground-truth examples from the prospectus to expand the benchmark.",
        "2. Fine-tune spaCy NER on domain-specific financial document data.",
        "3. Add a custom Presidio recognizer for Indian phone number formats (+91 prefix).",
        "4. Introduce post-processing rules to filter known false-positive patterns.",
    ]

    return "\n".join(lines)


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    """Define and parse CLI arguments for the evaluation script."""
    parser = argparse.ArgumentParser(
        description="Evaluate PII detection Precision, Recall, F1, and Accuracy.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=Path("evaluation/benchmark.json"),
        help="Path to the ground-truth benchmark JSON file.",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        default=Path("output/predictions.json"),
        help="Path to the predictions JSON file produced by redact_pii.py.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("output/evaluation_report.md"),
        help="Output path for the Markdown evaluation report.",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> None:
    """Entry point: load data, compute metrics, print results, save report."""
    args = parse_args(argv)

    if not args.benchmark.exists():
        logger.error("Benchmark file not found: %s", args.benchmark)
        sys.exit(1)

    if not args.predictions.exists():
        logger.error("Predictions file not found: %s", args.predictions)
        sys.exit(1)

    logger.info("Loading ground-truth benchmark from: %s", args.benchmark)
    ground_truth = load_records(args.benchmark)

    logger.info("Loading predictions from: %s", args.predictions)
    predictions = load_records(args.predictions)

    logger.info(
        "Evaluating %d ground-truth annotations against %d predictions …",
        len(ground_truth),
        len(predictions),
    )

    results = compute_metrics(ground_truth, predictions)

    logger.info("=" * 70)
    logger.info("%-20s %10s %10s %10s %10s", "ENTITY TYPE", "PRECISION", "RECALL", "F1", "ACCURACY")
    logger.info("=" * 70)
    for et in sorted(k for k in results if k != "AGGREGATE"):
        m = results[et]
        logger.info("%-20s %10.3f %10.3f %10.3f %10.3f", et, m.precision, m.recall, m.f1, m.accuracy)
    logger.info("-" * 70)
    agg = results.get("AGGREGATE")
    if agg:
        logger.info("%-20s %10.3f %10.3f %10.3f %10.3f", "AGGREGATE", agg.precision, agg.recall, agg.f1, agg.accuracy)
    logger.info("=" * 70)

    report_md = format_report(results, args.benchmark, args.predictions)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write(report_md)
    logger.info("Evaluation report saved to: %s", args.report)


if __name__ == "__main__":
    main()
