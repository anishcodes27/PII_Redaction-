# Enterprise PII Redaction Tool

A modular Python library and Streamlit web application for detecting and redacting Personally Identifiable Information (PII) from `.docx` documents. Replaces detected PII entities with realistic synthetic data via `Faker` while preserving run-level Word formatting.

---

## 1. Core Architecture & Detection Strategy

The engine uses a **3-Layer Hybrid Pipeline** to balance high precision on structured formats with high recall on contextual prose.

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
- **Regex Layer**: Compiled patterns for structured identifiers (`SSN`, `CREDIT_CARD`, `EMAIL`, `PHONE`, `IP_ADDRESS`, `DATE_OF_BIRTH`). Credit cards are validated against the **Luhn Algorithm** to filter false positives like internal account numbers.
- **spaCy NER (`en_core_web_lg`)**: Contextual entity recognition for `PERSON`, `ORG`, `ADDRESS` (mapped from `GPE`/`LOC`/`FAC`).
- **Microsoft Presidio (`AnalyzerEngine`)**: Secondary validation layer providing confidence scores and entity verification.

### Overlap & Conflict Resolution
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

## 3. Project Structure

```
pii_redaction/
├── app.py                  # Streamlit web dashboard
├── redact_pii.py           # Core CLI orchestrator
├── evaluate.py             # Benchmark evaluation engine
├── pii_detector.py         # Multi-layered detection pipeline
├── pii_replacer.py         # Faker replacement & consistency mapping
├── docx_handler.py         # DOCX run-level reader & writer
├── config.py               # Pattern definitions, model configs, blocklist
├── requirements.txt        # Pinned dependencies
├── data/
│   └── Red Herring Prospectus.docx
├── output/
│   ├── Redacted_Red_Herring_Prospectus.docx
│   ├── predictions.json
│   └── evaluation_report.md
└── evaluation/
    └── benchmark.json      # Ground-truth annotations
```

---

## 4. Environment Setup

### Prerequisites
- Python 3.10+

### Installation

```bash
# Clone and enter project directory
cd pii_redaction

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Upgrade packaging tools and install requirements
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

> **Note**: `requirements.txt` includes a direct wheel link for `en_core_web_lg-3.7.1`. No manual model download step is required.

---

## 5. Usage Guide

### Option A: Streamlit Web Dashboard

Launch the web interface for interactive document upload, PII selection, real-time metrics, and download:

```bash
streamlit run app.py
```

- Access at `http://localhost:8501`.
- Drag-and-drop `.docx` files.
- Toggle target entity types via sidebar checkboxes.
- View live metric cards and per-entity detection bar charts.
- Download the sanitized output file (`Redacted_<original_name>.docx`).

### Option B: CLI Batch Execution

Run redaction directly from the terminal:

```bash
python redact_pii.py \
    --input "data/Red Herring Prospectus.docx" \
    --output "output/Redacted_Red_Herring_Prospectus.docx" \
    --predictions-out "output/predictions.json"
```

CLI Arguments:
- `--input`: Input `.docx` file path.
- `--output`: Output `.docx` file path.
- `--predictions-out`: Path to write detection metadata JSON.
- `--log-level`: Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`).

---

## 6. Evaluation & Metrics Calculation

`evaluate.py` measures detection performance by matching predicted entity spans against `evaluation/benchmark.json`.

### Run Evaluation

```bash
python evaluate.py \
    --benchmark evaluation/benchmark.json \
    --predictions output/predictions.json \
    --report output/evaluation_report.md
```

### Metrics Definitions
- **Precision**: $\frac{TP}{TP + FP}$ — Fraction of detected entities that are true PII.
- **Recall**: $\frac{TP}{TP + FN}$ — Fraction of ground-truth PII entities successfully detected.
- **F1-Score**: $2 \times \frac{\text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}}$ — Harmonic mean.
- **Accuracy**: $\frac{TP}{TP + FP + FN}$ — Exact span match rate.

*Matching is evaluated on normalized `(entity_type, text)` pairs across document segments.*

---

## 7. Technical Trade-offs & Limitations

1. **Format Preservation vs. Run Splitting**:
   - `python-docx` breaks paragraph text into `Run` objects based on inline formatting changes (bold, italic, font styles). Replacing substrings across run boundaries requires clearing trailing runs while mutating the leading run's text node to maintain font styles.

2. **Precision vs. Recall in Financial Prose**:
   - Standard NER models tag capitalized legal terms (*Company*, *Prospectus*, *Board*) as `ORG`. We introduced `IGNORED_ENTITIES` filtering to prevent over-redaction, prioritizing Precision on generic document body text.

3. **Table Cell Boundaries**:
   - Table cells are evaluated as independent text segments. Entities broken across adjacent cells or hard paragraph breaks are evaluated separately, which can occasionally reduce contextual NER confidence scores.