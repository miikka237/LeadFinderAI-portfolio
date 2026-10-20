"""SQLite storage that makes runs resumable.

Four small tables:
  candidates       -- every domain ever discovered (cross-run deduplication)
  discovery_state  -- which search query to run next (the "cursor")
  ai_cache         -- raw LLM answers, so a domain is never paid for twice
  evaluations      -- the latest decision per domain

If a run stops halfway (crash, Ctrl+C, API quota), the next run picks up
from the stored cursor, reuses cached AI answers and counts ACCEPT rows
that already exist toward the target.
"""

import json
import sqlite3
from typing import Dict, List, Optional, Set

from .models import Candidate, Decision, LeadResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    domain        TEXT PRIMARY KEY,
    url           TEXT NOT NULL,
    source_query  TEXT,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS discovery_state (
    id                INTEGER PRIMARY KEY CHECK (id = 1),
    next_query_index  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_cache (
    domain         TEXT NOT NULL,
    query_version  INTEGER NOT NULL,
    raw_response   TEXT,
    PRIMARY KEY (domain, query_version)
);
CREATE TABLE IF NOT EXISTS evaluations (
    domain      TEXT PRIMARY KEY,
    decision    TEXT NOT NULL,
    row_json    TEXT NOT NULL,
    updated_at  TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


class Store:
    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path)
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # --- discovery ---------------------------------------------------------

    def add_candidate(self, candidate: Candidate) -> bool:
        """Insert a new candidate. Returns False if the domain was already known."""
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO candidates (domain, url, source_query) VALUES (?, ?, ?)",
            (candidate.domain, candidate.url, candidate.source_query),
        )
        self.conn.commit()
        return cur.rowcount == 1

    def all_candidates(self) -> List[Candidate]:
        rows = self.conn.execute(
            "SELECT url, domain, source_query FROM candidates ORDER BY rowid"
        ).fetchall()
        return [Candidate(url=u, domain=d, source_query=q) for u, d, q in rows]

    def get_cursor(self) -> int:
        row = self.conn.execute("SELECT next_query_index FROM discovery_state WHERE id = 1").fetchone()
        return row[0] if row else 0

    def set_cursor(self, next_index: int) -> None:
        self.conn.execute(
            "INSERT INTO discovery_state (id, next_query_index) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET next_query_index = excluded.next_query_index",
            (next_index,),
        )
        self.conn.commit()

    # --- AI cache ----------------------------------------------------------

    def get_ai_response(self, domain: str, query_version: int) -> Optional[str]:
        row = self.conn.execute(
            "SELECT raw_response FROM ai_cache WHERE domain = ? AND query_version = ?",
            (domain, query_version),
        ).fetchone()
        return row[0] if row else None

    def save_ai_response(self, domain: str, query_version: int, raw: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO ai_cache (domain, query_version, raw_response) VALUES (?, ?, ?)",
            (domain, query_version, raw),
        )
        self.conn.commit()

    # --- evaluations -------------------------------------------------------

    def save_result(self, result: LeadResult) -> None:
        self.conn.execute(
            "INSERT INTO evaluations (domain, decision, row_json) VALUES (?, ?, ?) "
            "ON CONFLICT(domain) DO UPDATE SET decision = excluded.decision, "
            "row_json = excluded.row_json, updated_at = CURRENT_TIMESTAMP",
            (result.domain, result.decision.value, json.dumps(result.as_row())),
        )
        self.conn.commit()

    def evaluated_domains(self) -> Set[str]:
        return {r[0] for r in self.conn.execute("SELECT domain FROM evaluations")}

    def accepted_domains(self) -> Set[str]:
        return {
            r[0] for r in self.conn.execute(
                "SELECT domain FROM evaluations WHERE decision = ?", (Decision.ACCEPT.value,)
            )
        }

    def rows_by_decision(self, decision: Decision) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT row_json FROM evaluations WHERE decision = ? ORDER BY domain",
            (decision.value,),
        ).fetchall()
        return [json.loads(r[0]) for r in rows]
