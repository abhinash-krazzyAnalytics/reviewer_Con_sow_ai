"""SQLite review history."""
import json
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.getenv("SOW_DB", "history.db")


def _conn(path=None):
    return sqlite3.connect(path or DB_PATH)


def init(path=None):
    with _conn(path) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, filename TEXT, score INTEGER,
            status TEXT, risk_level TEXT, knowledge_version TEXT, model TEXT, payload TEXT)""")


def save(result, path=None):
    with _conn(path) as c:
        c.execute("INSERT INTO reviews (ts, filename, score, status, risk_level, knowledge_version, model, payload)"
                  " VALUES (?,?,?,?,?,?,?,?)",
                  (datetime.now(timezone.utc).isoformat(timespec="seconds"), result["filename"], result["score"],
                   result["status"], result["risk_level"], result["meta"]["knowledge_version"],
                   result["meta"]["model"], json.dumps(result)))


def list_runs(limit=50, path=None):
    with _conn(path) as c:
        cur = c.execute("SELECT id, ts, filename, score, status, risk_level, knowledge_version, model "
                        "FROM reviews ORDER BY id DESC LIMIT ?", (limit,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
