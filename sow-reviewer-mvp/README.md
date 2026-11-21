# SOW Reviewer MVP (Python + Ollama)

## Setup
```
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
ollama pull llama3.1:8b                               # or any model you prefer
python setup_samples.py                               # creates sample_docs/ (.md .docx .pdf)
```

## Run
```
python dry_run.py            # offline checks of parser, verifier, score engine, exports, DB (no Ollama)
python dry_run.py --live     # same checks with the real Ollama agents
streamlit run app.py         # UI
```

## Settings (environment variables)
OLLAMA_MODEL (default llama3.1:8b), OLLAMA_HOST (default http://localhost:11434),
OLLAMA_NUM_CTX (default 8192; raise it for long SOWs), OLLAMA_TIMEOUT (seconds, default 180),
SOW_PARSER=fallback (skip Docling), SOW_DB (SQLite path, default history.db).

## Flow
app.py -> pipeline.py -> parser.py (Docling) -> agents.py (completeness + risk, then summary)
-> engine.py (quote verifier + score) -> exporter.py / db.py

## Where to change things
- Rules and severities: knowledge/checklist_v1.toon (add checklist_v2.toon and pass knowledge_path to switch)
- Penalties and thresholds: engine.py
- Prompts: agents.py
