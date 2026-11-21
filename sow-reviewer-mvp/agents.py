"""LLM agents (Ollama). Input: TOON rules + parsed SOW. Output: strict JSON, validated by pydantic."""
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal

import requests
from pydantic import BaseModel, ValidationError

DEFAULT_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")   # change to any model you have pulled
NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "180"))


# ---------- knowledge (TOON) ----------
@dataclass
class Checklist:
    version: str
    sections_toon: str
    risks_toon: str
    rules: dict      # rule_id -> {"kind", "severity", "name"}


_HEADER = re.compile(r"^(\w+)\[(\d+)\]\{([^}]*)\}:\s*$")


def _parse_blocks(text: str):
    blocks, current, buf = {}, None, []
    for line in text.splitlines():
        if not line.strip():
            continue
        m = _HEADER.match(line) if not line.startswith(" ") else None
        if m:
            current = (m.group(1), int(m.group(2)), [f.strip() for f in m.group(3).split(",")])
            blocks[current[0]] = {"n": current[1], "fields": current[2], "rows": [], "raw": [line]}
        elif current:
            name = current[0]
            # last column is free text and may contain commas -> split with a limit
            parts = [p.strip() for p in line.strip().split(",", len(current[2]) - 1)]
            if len(parts) != len(current[2]):
                raise ValueError(f"Bad TOON row in {name}: {line!r}")
            blocks[name]["rows"].append(dict(zip(current[2], parts)))
            blocks[name]["raw"].append(line)
    for name, b in blocks.items():
        if b["n"] != len(b["rows"]):
            raise ValueError(f"TOON block {name} declares {b['n']} rows but has {len(b['rows'])}")
    return blocks


def load_checklist(path) -> Checklist:
    path = Path(path)
    blocks = _parse_blocks(path.read_text(encoding="utf-8"))
    rules = {}
    for r in blocks["mandatory_sections"]["rows"]:
        rules[r["id"]] = {"kind": "section", "severity": r["severity"], "name": r["section"]}
    for r in blocks["risk_triggers"]["rows"]:
        rules[r["id"]] = {"kind": "risk", "severity": r["severity"], "name": r["pattern"]}
    return Checklist(path.stem, "\n".join(blocks["mandatory_sections"]["raw"]),
                     "\n".join(blocks["risk_triggers"]["raw"]), rules)


# ---------- output contract ----------
class Finding(BaseModel):
    rule_id: str
    category: Literal["Completeness", "Risk"]
    severity: Literal["CRITICAL", "HIGH", "MEDIUM"]
    section_detected: str
    issue_summary: str
    verbatim_quote: str
    recommended_fix: str


class AgentOutput(BaseModel):
    findings: List[Finding]
    executive_summary: str = ""


# Hand-written flat schema (no $ref) for Ollama's `format` parameter.
FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "string"},
                "category": {"type": "string", "enum": ["Completeness", "Risk"]},
                "severity": {"type": "string", "enum": ["CRITICAL", "HIGH", "MEDIUM"]},
                "section_detected": {"type": "string"},
                "issue_summary": {"type": "string"},
                "verbatim_quote": {"type": "string"},
                "recommended_fix": {"type": "string"}},
            "required": ["rule_id", "category", "severity", "section_detected",
                         "issue_summary", "verbatim_quote", "recommended_fix"]}},
        "executive_summary": {"type": "string"}},
    "required": ["findings"],
}
SUMMARY_SCHEMA = {"type": "object", "properties": {"executive_summary": {"type": "string"}},
                  "required": ["executive_summary"]}


# ---------- Ollama call ----------
def call_ollama(system: str, user: str, schema: dict, model=DEFAULT_MODEL, host=DEFAULT_HOST) -> str:
    payload = {
        "model": model, "stream": False, "format": schema,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "options": {"temperature": 0, "num_ctx": NUM_CTX},
    }
    try:
        r = requests.post(f"{host}/api/chat", json=payload, timeout=TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Ollama call failed at {host} with model '{model}': {e}. "
                           f"Is Ollama running and is the model pulled?") from e
    return r.json()["message"]["content"]


def _call_validated(system, user, schema, model, host, retries=1) -> AgentOutput:
    last_err = None
    for _ in range(retries + 1):
        content = call_ollama(system, user + (f"\n\nYour previous reply was invalid: {last_err}. "
                                              "Return valid JSON only." if last_err else ""),
                              schema, model, host)
        try:
            return AgentOutput.model_validate_json(content)
        except (ValidationError, ValueError) as e:
            last_err = str(e)[:300]
    raise RuntimeError(f"Model returned invalid JSON twice: {last_err}")


# ---------- agents ----------
COMPLETENESS_SYSTEM = """You are an SOW completeness auditor.
RULES are given in TOON tabular format: the first line lists the columns, each indented line is one rule.
Compare the SOW against EVERY rule. Report a finding ONLY for a rule whose section is missing or incomplete.
For each finding:
- rule_id: the rule id (e.g. SEC-03). category: "Completeness".
- section_detected: the exact heading in the SOW that covers it, or "MISSING" if there is none.
- verbatim_quote: text copied exactly from the SOW that shows the weakness; "" if the section is MISSING.
- recommended_fix: a concrete clause or table to add.
Never invent text. If the SOW satisfies all rules return {"findings": []}. Reply with JSON only."""

RISK_SYSTEM = """You are an SOW risk and vagueness auditor.
TRIGGERS are given in TOON tabular format. The pattern column lists risky phrases separated by ' / '.
Find places in the SOW that use these phrases or clearly equivalent wording.
For each occurrence:
- rule_id: the trigger id (e.g. RSK-01). category: "Risk".
- section_detected: the heading it appears under.
- verbatim_quote: the exact sentence copied character-for-character from the SOW. Do not paraphrase or fix typos.
- issue_summary and recommended_fix: one short sentence each.
Only report what is actually in the SOW. If nothing matches return {"findings": []}. Reply with JSON only."""

SUMMARY_SYSTEM = """You write a 3-4 sentence commercial risk overview for a Delivery Lead.
You receive verified findings and a score. Mention the most severe issues first. Do not add facts that
are not in the findings. Reply with JSON: {"executive_summary": "..."}"""


def completeness_agent(parsed, checklist, model=DEFAULT_MODEL, host=DEFAULT_HOST) -> AgentOutput:
    user = f"RULES:\n{checklist.sections_toon}\n\nSOW (markdown):\n{parsed.markdown}"
    return _call_validated(COMPLETENESS_SYSTEM, user, FINDINGS_SCHEMA, model, host)


def risk_agent(parsed, checklist, model=DEFAULT_MODEL, host=DEFAULT_HOST) -> AgentOutput:
    user = f"TRIGGERS:\n{checklist.risks_toon}\n\nSOW (markdown):\n{parsed.markdown}"
    return _call_validated(RISK_SYSTEM, user, FINDINGS_SCHEMA, model, host)


def summary_agent(scored, score_info, model=DEFAULT_MODEL, host=DEFAULT_HOST) -> str:
    brief = [{"rule_id": f["rule_id"], "severity": f["severity"], "issue": f["issue_summary"]} for f in scored]
    user = f"Score: {score_info['score']}/100 ({score_info['status']}).\nFindings: {json.dumps(brief)}"
    content = call_ollama(SUMMARY_SYSTEM, user, SUMMARY_SCHEMA, model, host)
    return json.loads(content)["executive_summary"]


def fallback_summary(scored, score_info) -> str:
    """Used when the summary agent fails or there is nothing to summarise."""
    c = score_info["counts"]
    if not scored:
        return f"No verified issues found. Score {score_info['score']}/100 ({score_info['status']})."
    top = "; ".join(f["issue_summary"] for f in scored if f["severity"] == "CRITICAL")[:400]
    return (f"Score {score_info['score']}/100 ({score_info['status']}): {c['CRITICAL']} critical, "
            f"{c['HIGH']} high, {c['MEDIUM']} medium findings." + (f" Critical: {top}" if top else ""))
