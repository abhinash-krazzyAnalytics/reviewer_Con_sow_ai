"""Orchestrator: parse -> agents -> verify -> score -> summary."""
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import agents
import engine
from parser import parse_document

KNOWLEDGE_PATH = Path(__file__).parent / "knowledge" / "checklist_v1.toon"


def run_review(path, model=agents.DEFAULT_MODEL, host=agents.DEFAULT_HOST,
               knowledge_path=KNOWLEDGE_PATH, completeness_fn=None, risk_fn=None,
               summary_fn=None, progress=None):
    """The *_fn arguments let tests replace the LLM calls (see dry_run.py)."""
    log = progress or (lambda msg: None)
    t0 = time.time()

    log("Parsing document")
    parsed = parse_document(path)
    checklist = agents.load_checklist(knowledge_path)

    approx_tokens = len(parsed.markdown) // 4
    warnings = list(parsed.warnings)
    if approx_tokens > agents.NUM_CTX * 0.6:
        warnings.append(f"SOW is about {approx_tokens} tokens; increase OLLAMA_NUM_CTX "
                        f"(now {agents.NUM_CTX}) or the model may ignore part of it.")

    c_fn = completeness_fn or (lambda p, c: agents.completeness_agent(p, c, model, host))
    r_fn = risk_fn or (lambda p, c: agents.risk_agent(p, c, model, host))

    log("Running completeness and risk agents")
    with ThreadPoolExecutor(max_workers=2) as pool:
        fc, fr = pool.submit(c_fn, parsed, checklist), pool.submit(r_fn, parsed, checklist)
        raw = [f.model_dump() for f in fc.result().findings] + [f.model_dump() for f in fr.result().findings]

    log("Verifying quotes and scoring")
    scored, needs_review = engine.process_findings(raw, parsed, checklist)
    info = engine.compute_score(scored)

    log("Writing summary")
    try:
        s_fn = summary_fn or (lambda s, i: agents.summary_agent(s, i, model, host))
        summary = s_fn(scored, info) if scored else agents.fallback_summary(scored, info)
    except Exception:
        summary = agents.fallback_summary(scored, info)

    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
    scored.sort(key=lambda f: order[f["severity"]])
    return {
        "filename": Path(path).name,
        **info,
        "executive_summary": summary,
        "findings": scored,
        "needs_review": needs_review,
        "meta": {"model": model, "knowledge_version": checklist.version,
                 "parser": parsed.parser_used, "section_fallback": parsed.section_fallback,
                 "warnings": warnings, "seconds": round(time.time() - t0, 1)},
    }
