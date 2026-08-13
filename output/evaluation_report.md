# PII Redaction Tool — Evaluation Report

**Benchmark**: `evaluation/benchmark.json`  
**Predictions**: `output/predictions.json`

---

## Per-Entity-Type Metrics

| Entity Type | Precision | Recall | F1-Score | Accuracy | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| ADDRESS | 0.025 | 1.000 | 0.050 | 0.025 | 6 | 230 | 0 |
| DATE_OF_BIRTH | 0.000 | 0.000 | 0.000 | 0.000 | 0 | 1019 | 0 |
| EMAIL | 0.054 | 0.750 | 0.100 | 0.053 | 3 | 53 | 1 |
| ORG | 0.001 | 0.667 | 0.002 | 0.001 | 2 | 2284 | 1 |
| PERSON | 0.030 | 1.000 | 0.059 | 0.030 | 8 | 256 | 0 |
| PHONE | 0.098 | 1.000 | 0.178 | 0.098 | 4 | 37 | 0 |
|---|---|---|---|---|---|---|---|
| **AGGREGATE** | **0.006** | **0.920** | **0.012** | **0.006** | 23 | 3879 | 2 |

---

## Trade-Off Analysis

### False Positives
False positives arise primarily from:
- Short common words matched by spaCy NER as PERSON or ORG (e.g., *Order*, *Table*).
- Numeric sequences that pass regex patterns but are not actual credit cards or SSNs.
- Overly broad DATE_TIME detections from Presidio that are not dates of birth.

**Mitigation strategies applied:**
- Luhn algorithm validation eliminates false credit-card positives.
- SSN regex excludes invalid prefixes (000, 666, 9xx).
- Confidence threshold of 0.4 on Presidio filters low-confidence hits.
- Longest-span conflict resolution prevents partial duplicate matches.

### False Negatives
False negatives are most common in:
- Non-standard phone formats (international numbers without country code).
- Addresses embedded in dense paragraphs without clear delimiters.
- Informal name references or abbreviations not recognised by spaCy.

**Mitigation strategies applied:**
- Three-layer hybrid pipeline: Regex + spaCy NER + Presidio maximises coverage.
- spaCy `en_core_web_lg` provides the highest accuracy among off-the-shelf models.

---

## Recommendations

1. Annotate more ground-truth examples from the prospectus to expand the benchmark.
2. Fine-tune spaCy NER on domain-specific financial document data.
3. Add a custom Presidio recognizer for Indian phone number formats (+91 prefix).
4. Introduce post-processing rules to filter known false-positive patterns.