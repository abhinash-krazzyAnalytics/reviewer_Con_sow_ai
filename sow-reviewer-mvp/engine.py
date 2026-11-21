"""Deterministic guardrails: quote verifier + score engine. No LLM is used here."""
import re
import unicodedata

PENALTY = {"CRITICAL": 20, "HIGH": 10, "MEDIUM": 5}
# One deduction per rule_id, so a chatty model cannot double-count the same risk.
PENALTY_ONCE_PER_RULE = True

# Heading keywords used to double-check an LLM claim that a section is MISSING.
SECTION_KEYWORDS = {
    "SEC-01": ["scope"],
    "SEC-02": ["deliverable"],
    "SEC-03": ["acceptance"],
    "SEC-04": ["raci", "responsibilit", "roles"],
    "SEC-05": ["commercial", "payment", "pricing", "fees"],
    "SEC-06": ["assumption", "dependenc"],
    "SEC-07": ["change control", "change request", "change management"],
}

_TRANSLATE = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u00a0": " ", "*": "", "_": "", "`": "",
})


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").translate(_TRANSLATE)
    return re.sub(r"\s+", " ", text).strip().casefold()


def process_findings(findings, parsed, checklist):
    """Verify raw LLM findings. Returns (scored, needs_review).

    scored       -> evidence checked, counts towards the score
    needs_review -> could not be verified; shown to the human, never scored
    """
    md_norm = normalize(parsed.markdown)
    headings = None if parsed.section_fallback else " | ".join(normalize(s["title"]) for s in parsed.sections)
    scored, review, seen, counted = [], [], set(), set()

    for raw in findings:
        f = dict(raw)
        rid = f.get("rule_id", "")
        rule = checklist.rules.get(rid)
        if rule is None:
            review.append({**f, "status": "unknown_rule_id"})
            continue

        f["severity"] = rule["severity"]           # severity always comes from the checklist
        f["category"] = "Completeness" if rule["kind"] == "section" else "Risk"
        quote = (f.get("verbatim_quote") or "").strip()
        missing = (f.get("section_detected") or "").strip().upper() == "MISSING"

        key = (rid, normalize(quote))
        if key in seen:
            continue
        seen.add(key)

        if quote:
            if normalize(quote) not in md_norm:
                review.append({**f, "status": "quote_not_found"})
                continue
            f["status"] = "verified"
        elif rule["kind"] == "section" and missing:
            if headings is None:
                f["status"] = "missing_unchecked"      # no headings to cross-check against
            elif any(k in headings for k in SECTION_KEYWORDS.get(rid, [])):
                review.append({**f, "status": "contradicted_by_headings"})
                continue
            else:
                f["status"] = "missing_confirmed"
        else:
            review.append({**f, "status": "no_quote"})
            continue

        f["counted"] = not (PENALTY_ONCE_PER_RULE and rid in counted)
        counted.add(rid)
        scored.append(f)

    return scored, review


def compute_score(scored):
    penalty = sum(PENALTY[f["severity"]] for f in scored if f.get("counted", True))
    score = max(0, 100 - penalty)
    if score >= 85:
        status, risk = "Approved", "Low Risk"
    elif score >= 65:
        status, risk = "Conditional / Needs Revision", "Medium Risk"
    else:
        status, risk = "Rejected", "High Risk"
    counts = {s: sum(1 for f in scored if f["severity"] == s) for s in PENALTY}
    return {"score": score, "status": status, "risk_level": risk, "counts": counts}
