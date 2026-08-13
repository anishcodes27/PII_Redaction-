# Enterprise PII Redaction Tool

A production-ready, modular Python CLI tool designed to detect and redact 9 specific types of Personally Identifiable Information (PII) from `.docx` documents. Replaces detected PII entities with realistic synthetic data using `Faker` while preserving original Word formatting.

---

## 1. Core Architecture & Hybrid Pipeline Strategy

The tool implements a **3-Layer Hybrid Pipeline** to balance high precision on structured formats with high recall on contextual prose.

```
┌─────────────────────────────────────────────────────────────────┐
│                    Input Document (.docx)                       │
└─────────────────────────────────────────────────────────────────┘
                                │
                        DocxReader Parsing
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Hybrid Detection Pipeline                    │
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐ │
│  │   Regex Layer    │  │    spaCy NER     │  │   Presidio    │ │
│  │ (SSN, CC, IP,    │  │ (en_core_web_lg: │  │  (Validation  │ │
│  │  Email, Phone)   │  │  PERSON, ORG)    │  │   & Scores)   │ │
│  └─────────┬────────┘  └────────┬─────────┘  └───────┬───────┘ │
└────────────┼────────────────────┼────────────────────┼─────────┘
             └────────────────────┼────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│             Conflict Resolution & Span Deduplication            │
│            (Longest-Match Priority + Score Threshold)           │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│             Synthetic Replacement (Faker Cache)                 │
│              (Same original → Same fake value)                  │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│              DocxWriter Run-Level Reconstitution                │
└─────────────────────────────────────────────────────────────────┘
```

### Detection Layers
- **Regex Layer**: Compiled patterns for structured identifiers (`SSN`, `CREDIT_CARD`, `EMAIL`, `PHONE`, `IP_ADDRESS`, `DATE_OF_BIRTH`). Credit card numbers are validated against the **Luhn Algorithm** to filter false positives like invoice/account numbers.
- **spaCy NER (`en_core_web_lg`)**: Contextual entity recognition for `PERSON`, `ORG`, `ADDRESS` (mapped from `GPE`/`LOC`/`FAC`).
- **Microsoft Presidio (`AnalyzerEngine`)**: Secondary validation layer providing confidence scores and entity verification.

### Overlap Resolution & False-Positive Filtering
When multiple layers detect overlapping character spans, `_resolve_overlaps()` applies:
1. **Longest-Span Priority**: Selects the broadest matching substring.
2. **Score Preference**: Resolves equal-length overlaps using detector confidence.
3. **Blocklist Filtering**: Strips common financial/legal terms (e.g., *Equity Shares*, *Floor Price*, *Company*, *SEBI*) via an explicit `IGNORED_ENTITIES` set.

### Entity-Level Consistency
To maintain document coherence, `FakerReplacer` utilizes a `ConsistencyCache`. If an entity (e.g., `"Kushal Hegde"`) appears multiple times across paragraphs or table cells, it receives the exact same synthetic replacement throughout the output file.

---

## 2. PII Entity Coverage

| # | Entity Type | Target Identifier | Detection Strategy | Synthetic Generator |
|---|---|---|---|---|
| 1 | Full Names | `PERSON` | spaCy NER + Presidio | `faker.name()` |
| 2 | Email Addresses | `EMAIL` | Regex + Presidio | `faker.email()` |
| 3 | Phone Numbers | `PHONE` | Regex + Presidio | `faker.phone_number()` |
| 4 | Company Names | `ORG` | spaCy NER + Presidio | `faker.company()` |
| 5 | Physical Addresses | `ADDRESS` | spaCy NER (`GPE`/`LOC`/`FAC`) | `faker.city()` |
| 6 | Social Security Numbers | `SSN` | Regex (Excludes invalid 000/666/9xx) | `faker.ssn()` |
| 7 | Credit Card Numbers | `CREDIT_CARD` | Regex + Luhn Validation | `faker.credit_card_number()` |
| 8 | Dates of Birth | `DATE_OF_BIRTH` | Contextual Regex + Presidio `DATE_TIME` | `faker.date_of_birth()` |
| 9 | IP Addresses | `IP_ADDRESS` | Regex Pattern Matching | `faker.ipv4_private()` |

---

## 3. Clean Project Structure

```
pii_redaction/
├── redact_pii.py           # Main CLI orchestrator
├── evaluate.py             # Benchmark evaluation engine
├── pii_detector.py         # Multi-layered detection pipeline
├── pii_replacer.py         # Faker replacement & consistency engine
├── docx_handler.py         # Word document run-level parser & writer
├── config.py               # Pattern definitions, model configs, blocklist
├── requirements.txt        # Dependencies
├── README.md               # Documentation & instructions
├── data/
│   └── Red Herring Prospectus.docx
├── evaluation/
│   └── benchmark.json      # Ground-truth annotations
└── output/
    ├── Redacted_Red_Herring_Prospectus.docx
    ├── predictions.json
    └── evaluation_report.md
```

---

## 4. Setup & Execution

### Prerequisites
- Python 3.10+

### Installation

```bash
# Navigate to project root
cd pii_redaction

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies and download spaCy model
pip install -r requirements.txt
python -m spacy download en_core_web_lg
```

### Running Redaction Script

```bash
python redact_pii.py \
    --input "data/Red Herring Prospectus.docx" \
    --output "output/Redacted_Red_Herring_Prospectus.docx" \
    --predictions-out "output/predictions.json"
```

### Running Evaluation Script

```bash
python evaluate.py \
    --benchmark evaluation/benchmark.json \
    --predictions output/predictions.json \
    --report output/evaluation_report.md
```

---

## 5. Evaluation & Performance Analysis

The evaluation script (`evaluate.py`) compares model predictions against `evaluation/benchmark.json` to calculate metrics:

- **Precision**: $\frac{TP}{TP + FP}$ — Fraction of detected entities that are true PII.
- **Recall**: $\frac{TP}{TP + FN}$ — Fraction of total ground-truth PII entities successfully detected.
- **F1-Score**: $2 \times \frac{\text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}}$ — Harmonic mean.
- **Accuracy**: $\frac{TP}{TP + FP + FN}$ — Exact span match rate across considered spans.

---

## 6. Technical Trade-offs & Limitations

1. **Format Preservation vs. Run Splitting**:
   - `python-docx` breaks paragraph text into `Run` objects based on inline formatting changes (bold, italic, font styles). Replacing substrings across run boundaries requires clearing trailing runs while mutating the leading run's text node to maintain font styles.

2. **Precision vs. Recall in Financial Prose**:
   - Standard NER models tag capitalized legal terms (*Company*, *Prospectus*, *Board*) as `ORG`. We introduced `IGNORED_ENTITIES` filtering to prevent over-redaction, prioritizing Precision on generic document body text.

3. **Table Cell Boundaries**:
   - Table cells are evaluated as independent text segments. Entities broken across adjacent cells or hard paragraph breaks are evaluated separately, which can occasionally reduce contextual NER confidence scores.