"""Excel (.xlsx) and Markdown (.md) report generators."""
import io

import pandas as pd

COLS = ["severity", "rule_id", "section_detected", "issue_summary", "verbatim_quote", "recommended_fix", "status"]
HEAD = ["Severity", "Rule", "Section", "Issue", "Verbatim Quote", "Recommended Fix", "Evidence"]


def findings_df(result) -> pd.DataFrame:
    rows = [{h: f.get(c, "") for c, h in zip(COLS, HEAD)} for f in result["findings"]]
    return pd.DataFrame(rows, columns=HEAD)


def review_df(result) -> pd.DataFrame:
    rows = [{"Rule": f.get("rule_id", ""), "Why not scored": f.get("status", ""),
             "Issue": f.get("issue_summary", ""), "Quote the model gave": f.get("verbatim_quote", "")}
            for f in result["needs_review"]]
    return pd.DataFrame(rows, columns=["Rule", "Why not scored", "Issue", "Quote the model gave"])


def to_excel(result) -> bytes:
    summary = pd.DataFrame([
        ("File", result["filename"]), ("Score", result["score"]), ("Status", result["status"]),
        ("Risk level", result["risk_level"]), ("Executive summary", result["executive_summary"]),
        ("Model", result["meta"]["model"]), ("Knowledge version", result["meta"]["knowledge_version"]),
        ("Parser", result["meta"]["parser"]),
    ], columns=["Field", "Value"])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        summary.to_excel(xw, sheet_name="Summary", index=False)
        findings_df(result).to_excel(xw, sheet_name="Findings", index=False)
        review_df(result).to_excel(xw, sheet_name="Needs human review", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(
                    60, max(12, max(len(str(c.value or "")) for c in col) + 2))
    return buf.getvalue()


def _cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def to_markdown(result) -> str:
    m = result["meta"]
    out = [f"# SOW Review: {result['filename']}", "",
           f"**Score:** {result['score']}/100  |  **Status:** {result['status']}  |  **Risk:** {result['risk_level']}", "",
           "## Executive summary", result["executive_summary"], "", "## Findings", ""]
    if result["findings"]:
        out += ["| Severity | Rule | Section | Issue | Verbatim quote | Recommended fix |", "|---|---|---|---|---|---|"]
        for f in result["findings"]:
            out.append("| " + " | ".join(_cell(f.get(k, "")) for k in
                       ["severity", "rule_id", "section_detected", "issue_summary", "verbatim_quote", "recommended_fix"]) + " |")
    else:
        out.append("No verified findings.")
    if result["needs_review"]:
        out += ["", "## Needs human review (not scored)", ""]
        out += [f"- {f.get('rule_id', '?')} ({f.get('status')}): {f.get('issue_summary', '')}" for f in result["needs_review"]]
    out += ["", f"_Model: {m['model']} | Knowledge: {m['knowledge_version']} | Parser: {m['parser']} | {m['seconds']}s_"]
    return "\n".join(out)
