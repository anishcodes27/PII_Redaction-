"""
PII Redaction Web Application.

Streamlit-based dashboard allowing users to upload .docx files, select target
PII entity types, view detection metrics, evaluate accuracy against benchmark, and download redacted documents.
"""

from __future__ import annotations

import tempfile
from collections import defaultdict
from pathlib import Path
import streamlit as st
import pandas as pd

from config import ENTITY_TYPES
from docx_handler import DocxReader, DocxWriter
from pii_detector import HybridDetector, PIISpan
from pii_replacer import FakerReplacer
from evaluate import load_records, compute_metrics, EntityRecord


st.set_page_config(
    page_title="Enterprise PII Redaction Tool",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# Pre-warm detection models on app load
@st.cache_resource
def get_hybrid_detector() -> HybridDetector:
    """Cache the HybridDetector instance across app reruns."""
    return HybridDetector()


@st.cache_resource
def get_faker_replacer() -> FakerReplacer:
    """Cache the FakerReplacer instance across app reruns."""
    return FakerReplacer()


def main() -> None:
    st.title("🛡️ Enterprise PII Redaction Tool")
    st.markdown(
        "Upload any `.docx` document to automatically detect sensitive Personally Identifiable Information (PII) "
        "and replace it with consistent, realistic synthetic data powered by **Faker**, **spaCy NER**, and **Microsoft Presidio**."
    )
    st.divider()

    detector = get_hybrid_detector()
    replacer = get_faker_replacer()

    st.sidebar.header("⚙️ Configuration")

    all_entity_labels = list(ENTITY_TYPES.keys())
    selected_entities = st.sidebar.multiselect(
        "Select PII Entity Types to Redact",
        options=all_entity_labels,
        default=all_entity_labels,
        help="Deselect any entity type you wish to keep in the final document.",
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "**Supported PII Types:**\n"
        "- 👤 Full Names (`PERSON`)\n"
        "- ✉️ Emails (`EMAIL`)\n"
        "- 📞 Phone Numbers (`PHONE`)\n"
        "- 🏢 Organisations (`ORG`)\n"
        "- 📍 Addresses (`ADDRESS`)\n"
        "- 💳 Credit Cards (`CREDIT_CARD`)\n"
        "- 🆔 SSN (`SSN`)\n"
        "- 📅 DOB (`DATE_OF_BIRTH`)\n"
        "- 🌐 IP Addresses (`IP_ADDRESS`)"
    )

    uploaded_file = st.file_uploader(
        "Upload Document (.docx)",
        type=["docx"],
        help="Select a Microsoft Word document (.docx) to process.",
    )

    if uploaded_file is None:
        st.info("👆 Please upload a `.docx` file using the file uploader above to begin.")
        return

    if not uploaded_file.name.lower().endswith(".docx"):
        st.error("⚠️ Invalid file format. Please upload a `.docx` document.")
        return

    st.success(f"📁 Loaded file: **{uploaded_file.name}** ({uploaded_file.size / 1024:.1f} KB)")

    if not selected_entities:
        st.warning("⚠️ Please select at least one PII entity type to redact from the sidebar.")
        return

    if st.button("🚀 Redact Document", type="primary"):
        status_box = st.status("⏳ **Processing Document in Progress...** Please wait while the NLP engine scans paragraphs and tables.", expanded=True)

        with status_box:
            st.write("📄 Extracting text segments from Word document...")
            progress_bar = st.progress(0, text="Reading document text segments...")

            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_in:
                    tmp_in.write(uploaded_file.getvalue())
                    tmp_in_path = Path(tmp_in.name)

                reader = DocxReader(tmp_in_path)
                segments = reader.extract_segments()

                if not segments:
                    st.warning("⚠️ The uploaded document appears to be empty or contains no readable text.")
                    progress_bar.empty()
                    status_box.update(label="❌ Document was empty", state="error")
                    return

                seen_originals = {}
                entity_counts = defaultdict(int)
                prediction_records = []

                total_segments = len(segments)
                st.write(f"📄 Found **{total_segments}** text segments across paragraphs and tables.")

                for seg_idx, seg in enumerate(segments):
                    if seg_idx % 5 == 0 or seg_idx == total_segments - 1:
                        pct = int(((seg_idx + 1) / total_segments) * 70)
                        progress_bar.progress(pct, text=f"Scanning segment {seg_idx + 1}/{total_segments} ({pct}%) for PII...")

                    spans: list[PIISpan] = detector.detect(seg.text)
                    for span in spans:
                        if span.entity_type not in selected_entities:
                            continue
                        original = span.text.strip()
                        if not original:
                            continue
                        if original not in seen_originals:
                            fake = replacer.replace(span.entity_type, original)
                            seen_originals[original] = fake
                        entity_counts[span.entity_type] += 1
                        prediction_records.append(
                            EntityRecord(
                                segment_index=seg_idx,
                                start=span.start,
                                end=span.end,
                                entity_type=span.entity_type,
                                text=original,
                            )
                        )

                replacements = list(seen_originals.items())
                st.write(f"✨ Found **{len(replacements)}** unique PII items to replace with synthetic Faker data.")

                progress_bar.progress(85, text=f"Applying {len(replacements)} synthetic replacements to Word formatting runs...")
                writer = DocxWriter(reader.document)
                writer.apply_replacements(replacements)

                progress_bar.progress(95, text="Rebuilding redacted Word document...")
                out_filename = f"Redacted_{uploaded_file.name}"
                tmp_out_path = Path(tempfile.gettempdir()) / out_filename
                writer.save(tmp_out_path)

                with open(tmp_out_path, "rb") as f_out:
                    redacted_bytes = f_out.read()

                tmp_in_path.unlink(missing_ok=True)
                tmp_out_path.unlink(missing_ok=True)

                progress_bar.progress(100, text="Complete!")
                status_box.update(label="✅ **Redaction Completed Successfully!**", state="complete", expanded=False)

            except Exception as e:
                progress_bar.empty()
                status_box.update(label="❌ Redaction Failed", state="error")
                st.error(f"❌ An error occurred during document processing: {str(e)}")
                return

        st.balloons()
        st.subheader("📊 Detection & Replacement Dashboard")

        total_detected = sum(entity_counts.values())

        cols = st.columns(4)
        cols[0].metric("Total Spans Detected", total_detected)
        cols[1].metric("Unique PII Replaced", len(replacements))
        cols[2].metric("Entity Types Selected", len(selected_entities))
        cols[3].metric("Segments Scanned", len(segments))

        if entity_counts:
            st.write("#### Detection Breakdown by Entity Type")
            chart_data = {"Entity Type": list(entity_counts.keys()), "Detections": list(entity_counts.values())}
            st.bar_chart(data=chart_data, x="Entity Type", y="Detections")

        st.divider()
        st.subheader("📈 Model Evaluation Metrics (Benchmark Analysis)")

        benchmark_path = Path("evaluation/benchmark.json")
        if benchmark_path.exists():
            ground_truth = load_records(benchmark_path)
            eval_results = compute_metrics(ground_truth, prediction_records)

            agg = eval_results.get("AGGREGATE")
            if agg:
                m_cols = st.columns(4)
                m_cols[0].metric("Overall Precision", f"{agg.precision:.1%}")
                m_cols[1].metric("Overall Recall", f"{agg.recall:.1%}")
                m_cols[2].metric("Overall F1-Score", f"{agg.f1:.1%}")
                m_cols[3].metric("Overall Accuracy", f"{agg.accuracy:.1%}")

            table_rows = []
            for etype in sorted(k for k in eval_results if k != "AGGREGATE"):
                res = eval_results[etype]
                table_rows.append(
                    {
                        "Entity Type": etype,
                        "Precision": f"{res.precision:.3f}",
                        "Recall": f"{res.recall:.3f}",
                        "F1-Score": f"{res.f1:.3f}",
                        "Accuracy": f"{res.accuracy:.3f}",
                        "True Positives (TP)": res.true_positives,
                        "False Positives (FP)": res.false_positives,
                        "False Negatives (FN)": res.false_negatives,
                    }
                )

            st.write("#### Detailed Per-Entity Metrics")
            st.dataframe(pd.DataFrame(table_rows), use_container_width=True)
        else:
            st.info("ℹ️ No benchmark file found at `evaluation/benchmark.json` to calculate evaluation metrics.")

        st.divider()
        st.download_button(
            label="💾 Download Redacted Document",
            data=redacted_bytes,
            file_name=out_filename,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary",
        )


if __name__ == "__main__":
    main()
