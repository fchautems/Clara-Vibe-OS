from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .contracts import utc, validate


class Journal:
    """Propriétaire unique : le travailleur de coordination, jamais le thread audio."""
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=2)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS actions (
                action_id TEXT PRIMARY KEY, request_id TEXT NOT NULL,
                step_id TEXT NOT NULL, attempt_no INTEGER NOT NULL,
                payload TEXT NOT NULL, result TEXT,
                UNIQUE(request_id, step_id, attempt_no));
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL,
                kind TEXT NOT NULL, payload TEXT NOT NULL);
        """)
        # No replay after restart, even for an opening that may already have happened.
        for aid, in self.db.execute("SELECT action_id FROM actions WHERE result IS NULL").fetchall():
            self.db.execute("UPDATE actions SET result=? WHERE action_id=?",
                            (json.dumps({"status": "UNKNOWN", "reason": "RESTART_NO_REPLAY"}), aid))
        self.db.commit()

    def event(self, kind: str, payload: dict):
        self.db.execute("INSERT INTO events(timestamp,kind,payload) VALUES (?,?,?)",
                        (utc(), kind, json.dumps(payload, ensure_ascii=False)))
        self.db.commit()

    def prepare(self, action: dict) -> bool:
        validate("ActionRequest", action)
        data = json.dumps(action, ensure_ascii=False, sort_keys=True)
        old = self.db.execute("SELECT payload FROM actions WHERE request_id=? AND step_id=? AND attempt_no=?",
                              (action["request_id"], action["step_id"], action["attempt_no"])).fetchone()
        if old:
            if old[0] != data:
                raise ValueError("Collision de déduplication")
            return False
        self.db.execute("INSERT INTO actions(action_id,request_id,step_id,attempt_no,payload) VALUES (?,?,?,?,?)",
                        (action["action_id"], action["request_id"], action["step_id"], action["attempt_no"], data))
        self.db.commit()
        return True

    def finish(self, result: dict):
        validate("ActionResult", result)
        self.db.execute("UPDATE actions SET result=? WHERE action_id=?",
                        (json.dumps(result, ensure_ascii=False), result["action_id"]))
        self.db.commit()

    def close(self):
        self.db.close()
