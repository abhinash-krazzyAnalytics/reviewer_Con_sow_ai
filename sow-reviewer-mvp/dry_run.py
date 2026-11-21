"""Dry run for the scoring engine and quote verifier.

  python dry_run.py          # offline: rule-based STAND-IN agents replace the LLM (no Ollama needed)
  python dry_run.py --live   # real Ollama agents (checks the model, slower, results may vary)

The offline mode proves the deterministic parts (parser, quote verifier, score engine, exports, DB).
It does NOT measure how accurate your Ollama model is - use --live for that.
"""
import re
import sys
import tempfile
from pathlib import Path

import db
import engine
import exporter
from agents import AgentOutput, Finding
from engine import normalize
from pipeline import run_review

SAMPLES = Path(__file__).parent / "sample_docs"
LIVE = "--live" in sys.argv

# ---------------- stand-in agents (offline mode only) ----------------
SECTION_RULES = {  # rule_id: (heading keywords, fix)
    "SEC-02": (["deliverable"], "Add a deliverables table with ID, Deliverable, Format, Target Date and Owner."),
    "SEC-03": (["acceptance"], "Add measurable acceptance criteria per deliverable and a review window with deemed acceptance."),
    "SEC-04": (["responsibilit", "raci"], "Add a RACI table and name the Vendor and Client leads."),
    "SEC-05": (["commercial", "payment"], "State TCV, milestone billing triggers and payment terms."),
    "SEC-06": (["assumption"], "List client dependencies and what happens if dates slip."),
    "SEC-07": (["change control"], "Require a signed written Change Request for scope, schedule or cost changes."),
}
RISK_RULES = {
    "RSK-01": (r"full satisfaction|as required by client", "Replace with measurable acceptance criteria."),
    "RSK-02": (r"unlimited revisions|ongoing maintenance included", "Cap revision rounds and define the warranty period."),
    "RSK-03": (r"best efforts", "Replace with a specific, measurable obligation."),
    "RSK-04": (r"\bTBD\b|to be finalized at kickoff", "Replace with dates or date-setting rules."),
}


def _heading_line(text, keywords):
    for line in text.splitlines():
        s = line.strip().lstrip("#").strip()
        if 3 < len(s) < 80 and any(k in s.lower() for k in keywords) and (line.lstrip().startswith("#") or s[:2].rstrip(".").isdigit()):
            return s
    return None


def mock_completeness(parsed, checklist):
    text, out = parsed.markdown, []
    scope = _heading_line(text, ["scope"])
    if scope is None:
        out.append(("SEC-01", "MISSING", "", "Scope section is missing.", "Add In-Scope and Out-of-Scope sections."))
    elif not re.search(r"out[- ]of[- ]scope", text, re.I):
        out.append(("SEC-01", scope, scope, "No Out-of-Scope boundaries defined.", "Add an explicit Out-of-Scope list."))
    for rid, (kws, fix) in SECTION_RULES.items():
        if _heading_line(text, kws) is None:
            out.append((rid, "MISSING", "", f"{checklist.rules[rid]['name']} is missing.", fix))
    findings = [Finding(rule_id=r, category="Completeness", severity="CRITICAL", section_detected=s,
                        issue_summary=i, verbatim_quote=q, recommended_fix=f) for r, s, q, i, f in out]
    # deliberate LLM-style mistake: claims a section is missing although its heading exists
    if not parsed.section_fallback and _heading_line(text, ["commercial", "payment"]):
        findings.append(Finding(rule_id="SEC-05", category="Completeness", severity="CRITICAL", section_detected="MISSING",
                                issue_summary="(injected false claim)", verbatim_quote="", recommended_fix="n/a"))
    return AgentOutput(findings=findings)


def mock_risk(parsed, checklist):
    flat = re.sub(r"\s+", " ", parsed.markdown)
    sentences = re.split(r"(?<=[.!?])\s+", flat)
    findings = []
    for rid, (pattern, fix) in RISK_RULES.items():
        m = re.search(pattern, flat, re.I)
        if not m:
            continue
        if rid == "RSK-04":   # table cells: quote a short window
            quote = flat[max(0, m.start() - 40): m.end() + 20].strip()
        else:
            quote = next(s for s in sentences if re.search(pattern, s, re.I))
        findings.append(Finding(rule_id=rid, category="Risk", severity="CRITICAL", section_detected="(see quote)",
                                issue_summary=f"Risky wording matched {rid}.", verbatim_quote=quote, recommended_fix=fix))
    # deliberate hallucination: a quote that is not in the SOW
    findings.append(Finding(rule_id="RSK-03", category="Risk", severity="HIGH", section_detected="n/a",
                            issue_summary="(injected hallucination)",
                            verbatim_quote="The Vendor guarantees 24/7 support at no additional charge.",
                            recommended_fix="n/a"))
    return AgentOutput(findings=findings)


# ---------------- checks ----------------
fails = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        fails.append(msg)


def unit_tests():
    print("\n[1] Engine unit tests")
    check(normalize("The Client\u2019s  full\nsatisfaction") == "the client's full satisfaction", "normalize handles curly quotes + whitespace")
    mk = lambda *sevs: [{"severity": v, "counted": True} for v in sevs]
    sc = lambda *sevs: engine.compute_score(mk(*sevs))
    check(sc()["score"] == 100, "no findings -> 100")
    check(sc("CRITICAL", "CRITICAL", "CRITICAL", "CRITICAL", "HIGH")["score"] == 10, "4 critical + 1 high -> 10")
    check(sc(*["CRITICAL"] * 6)["score"] == 0, "score never goes below 0")
    check(sc("HIGH", "MEDIUM")["score"] == 85 and sc("HIGH", "MEDIUM")["status"] == "Approved", "85 -> Approved / Low Risk")
    check(sc("HIGH", "HIGH")["score"] == 80 and sc("HIGH", "HIGH")["status"].startswith("Conditional"), "80 -> Conditional")
    check(sc("CRITICAL", "MEDIUM", "MEDIUM", "MEDIUM")["score"] == 65 and
          sc("CRITICAL", "MEDIUM", "MEDIUM", "MEDIUM")["status"].startswith("Conditional"), "65 -> Conditional (lower bound)")
    check(sc("CRITICAL", "CRITICAL")["score"] == 60 and sc("CRITICAL", "CRITICAL")["status"] == "Rejected", "60 -> Rejected / High Risk")
    dup = [{"severity": "CRITICAL", "counted": True}, {"severity": "CRITICAL", "counted": False}]
    check(engine.compute_score(dup)["score"] == 80, "repeat findings of the same rule are not double-counted")


def run_doc(path):
    if LIVE:
        return run_review(path)
    return run_review(path, completeness_fn=mock_completeness, risk_fn=mock_risk,
                      summary_fn=lambda s, i: "stand-in summary")


def doc_tests():
    results = {}
    for fmt in ["md", "docx", "pdf"]:
        print(f"\n[2] Correct SOW (.{fmt})")
        r = run_doc(SAMPLES / f"correct_sow_sample.{fmt}")
        results[("correct", fmt)] = r
        print(f"      score={r['score']} status={r['status']} parser={r['meta']['parser']} fallback_sections={r['meta']['section_fallback']}")
        check(90 <= r["score"] <= 100, f"score {r['score']} is within 90-100")
        check(r["counts"]["CRITICAL"] == 0 and r["counts"]["HIGH"] == 0, "0 CRITICAL and 0 HIGH findings")
        if not LIVE:
            reasons = {f["status"] for f in r["needs_review"]}
            check("quote_not_found" in reasons, "hallucinated quote was caught and not scored")
            if not r["meta"]["section_fallback"]:
                check("contradicted_by_headings" in reasons, "false 'section MISSING' claim was caught")

        print(f"\n[3] Incorrect SOW (.{fmt})")
        r = run_doc(SAMPLES / f"incorrect_sow_sample.{fmt}")
        results[("incorrect", fmt)] = r
        print(f"      score={r['score']} status={r['status']} counts={r['counts']}")
        check(r["score"] < 40 and r["status"] == "Rejected", f"score {r['score']} < 40 and Rejected")
        rules = {f["rule_id"]: f for f in r["findings"]}
        for rid in ["SEC-03", "SEC-04", "SEC-01", "SEC-07", "SEC-06", "RSK-01", "RSK-02", "RSK-04"]:
            check(rid in rules, f"caught {rid}")
        q = lambda rid: normalize(rules.get(rid, {}).get("verbatim_quote", ""))
        check("full satisfaction" in q("RSK-01"), "RSK-01 quote contains 'full satisfaction'")
        check("unlimited revisions to the chatbot prompts and ui are included" in q("RSK-02"), "RSK-02 quote is the unlimited-revisions sentence")
        md_norm = normalize(engine_text(SAMPLES / f"incorrect_sow_sample.{fmt}"))
        quoted = [f for f in r["findings"] if f["verbatim_quote"]]
        check(all(normalize(f["verbatim_quote"]) in md_norm for f in quoted), f"100% of {len(quoted)} scored quotes are verbatim in the parsed text")
    return results


def engine_text(path):
    from parser import parse_document
    return parse_document(path).markdown


def export_and_db_tests(result):
    print("\n[4] Exports and history DB")
    xlsx = exporter.to_excel(result)
    check(xlsx[:2] == b"PK" and len(xlsx) > 2000, "Excel export produced a valid .xlsx (zip) file")
    md = exporter.to_markdown(result)
    check("| Severity |" in md and result["filename"] in md, "Markdown report contains the findings table")
    with tempfile.TemporaryDirectory() as tmp:
        p = str(Path(tmp) / "t.db")
        db.init(p)
        db.save(result, p)
        rows = db.list_runs(path=p)
        check(len(rows) == 1 and rows[0]["score"] == result["score"], "run saved to and read back from SQLite")


if __name__ == "__main__":
    print("MODE:", "LIVE (Ollama)" if LIVE else "OFFLINE (stand-in agents)")
    unit_tests()
    res = doc_tests()
    export_and_db_tests(res[("incorrect", "md")])
    print("\n" + ("ALL CHECKS PASSED" if not fails else f"{len(fails)} CHECK(S) FAILED"))
    sys.exit(1 if fails else 0)
