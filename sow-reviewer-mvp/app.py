"""Streamlit UI. Run:  streamlit run app.py"""
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

import db
import exporter
from agents import DEFAULT_HOST, DEFAULT_MODEL
from pipeline import run_review

st.set_page_config(page_title="SOW Reviewer", layout="wide")
db.init()

with st.sidebar:
    st.header("Settings")
    model = st.text_input("Ollama model", DEFAULT_MODEL)
    host = st.text_input("Ollama host", DEFAULT_HOST)

review_tab, history_tab = st.tabs(["Review", "History"])

with review_tab:
    st.title("SOW Reviewer")
    upload = st.file_uploader("Upload a draft SOW", type=["pdf", "docx", "md"])
    if st.button("Run SOW Review", type="primary", disabled=upload is None):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / upload.name
            path.write_bytes(upload.getvalue())
            try:
                with st.status("Reviewing...", expanded=True) as status:
                    result = run_review(path, model=model, host=host, progress=st.write)
                    status.update(label=f"Done in {result['meta']['seconds']}s", state="complete")
                db.save(result)
                st.session_state["result"] = result
            except Exception as e:
                st.error(str(e))

    result = st.session_state.get("result")
    if result:
        c1, c2, c3 = st.columns(3)
        c1.metric("Score", f"{result['score']}/100")
        c2.metric("Status", result["status"])
        c3.metric("Risk level", result["risk_level"])
        {"Low Risk": st.success, "Medium Risk": st.warning, "High Risk": st.error}[result["risk_level"]](
            result["executive_summary"])
        for w in result["meta"]["warnings"]:
            st.info(w)

        st.subheader("Findings")
        df = exporter.findings_df(result)
        if df.empty:
            st.write("No verified findings.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)

        if result["needs_review"]:
            with st.expander(f"Needs human review ({len(result['needs_review'])}) - not included in the score"):
                st.dataframe(exporter.review_df(result), use_container_width=True, hide_index=True)

        d1, d2 = st.columns(2)
        stem = Path(result["filename"]).stem
        d1.download_button("Download Excel", exporter.to_excel(result), f"{stem}_review.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        d2.download_button("Download Markdown", exporter.to_markdown(result), f"{stem}_review.md", "text/markdown")

with history_tab:
    runs = db.list_runs()
    if runs:
        st.dataframe(pd.DataFrame(runs), use_container_width=True, hide_index=True)
    else:
        st.write("No reviews yet.")
