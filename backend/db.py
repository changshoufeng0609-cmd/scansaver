"""SQLite data layer. Hackathon-simple: JSON blobs in TEXT columns, no ORM."""
import json
import sqlite3
import time
import uuid
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "scansaver.db"


def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS specs (
              id TEXT PRIMARY KEY,
              vertical TEXT,
              spec_json TEXT,
              confirmed INTEGER DEFAULT 0,
              created_at REAL
            );
            CREATE TABLE IF NOT EXISTS calls (
              conversation_id TEXT PRIMARY KEY,
              spec_id TEXT,
              facility_name TEXT,
              negotiation_mode INTEGER DEFAULT 0,
              status TEXT,
              transcript_json TEXT,
              raw_webhook_json TEXT,
              created_at REAL
            );
            CREATE TABLE IF NOT EXISTS quotes (
              id TEXT PRIMARY KEY,
              spec_id TEXT,
              facility_name TEXT,
              line_items_json TEXT,
              total REAL,
              itemized INTEGER,
              read_included INTEGER,
              notes TEXT,
              red_flags_json TEXT,
              created_at REAL
            );
            CREATE TABLE IF NOT EXISTS outcomes (
              id TEXT PRIMARY KEY,
              spec_id TEXT,
              facility_name TEXT,
              outcome_type TEXT,
              details TEXT,
              red_flags_json TEXT,
              created_at REAL
            );
            """
        )


def _rows(rows):
    return [dict(r) for r in rows]


# ---- specs ----

def create_spec(spec: dict, vertical: str, confirmed: bool = False) -> str:
    spec_id = uuid.uuid4().hex[:8]
    with _conn() as c:
        c.execute(
            "INSERT INTO specs (id, vertical, spec_json, confirmed, created_at) VALUES (?,?,?,?,?)",
            (spec_id, vertical, json.dumps(spec), int(confirmed), time.time()),
        )
    return spec_id


def update_spec(spec_id: str, spec: dict):
    with _conn() as c:
        c.execute("UPDATE specs SET spec_json=? WHERE id=?",
                  (json.dumps(spec), spec_id))


def confirm_spec(spec_id: str):
    with _conn() as c:
        c.execute("UPDATE specs SET confirmed=1 WHERE id=?", (spec_id,))


def get_spec(spec_id: str):
    with _conn() as c:
        r = c.execute("SELECT * FROM specs WHERE id=?", (spec_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["spec"] = json.loads(d.pop("spec_json"))
    return d


def latest_spec(confirmed_only: bool = False):
    q = "SELECT * FROM specs"
    if confirmed_only:
        q += " WHERE confirmed=1"
    q += " ORDER BY created_at DESC LIMIT 1"
    with _conn() as c:
        r = c.execute(q).fetchone()
    if not r:
        return None
    d = dict(r)
    d["spec"] = json.loads(d.pop("spec_json"))
    return d


# ---- calls ----

def upsert_call(conversation_id: str, spec_id: str = None, facility_name: str = None,
                negotiation_mode: bool = None, status: str = None,
                transcript: list = None, raw_webhook: dict = None):
    with _conn() as c:
        exists = c.execute(
            "SELECT 1 FROM calls WHERE conversation_id=?", (conversation_id,)
        ).fetchone()
        if not exists:
            c.execute(
                "INSERT INTO calls (conversation_id, created_at) VALUES (?,?)",
                (conversation_id, time.time()),
            )
        sets, vals = [], []
        for col, val in [
            ("spec_id", spec_id),
            ("facility_name", facility_name),
            ("negotiation_mode", None if negotiation_mode is None else int(negotiation_mode)),
            ("status", status),
            ("transcript_json", None if transcript is None else json.dumps(transcript)),
            ("raw_webhook_json", None if raw_webhook is None else json.dumps(raw_webhook)),
        ]:
            if val is not None:
                sets.append(f"{col}=?")
                vals.append(val)
        if sets:
            vals.append(conversation_id)
            c.execute(f"UPDATE calls SET {', '.join(sets)} WHERE conversation_id=?", vals)


def get_call(conversation_id: str):
    with _conn() as c:
        r = c.execute("SELECT * FROM calls WHERE conversation_id=?", (conversation_id,)).fetchone()
    return dict(r) if r else None


def list_calls(spec_id: str):
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM calls WHERE spec_id=? ORDER BY created_at", (spec_id,)
        ).fetchall()
    return _rows(rows)


# ---- quotes ----

def save_quote(spec_id: str, facility_name: str, line_items: list, total: float,
               itemized: bool, read_included: bool, notes: str, red_flags: list) -> str:
    qid = uuid.uuid4().hex[:8]
    with _conn() as c:
        c.execute(
            """INSERT INTO quotes (id, spec_id, facility_name, line_items_json, total,
               itemized, read_included, notes, red_flags_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (qid, spec_id, facility_name, json.dumps(line_items), total,
             int(itemized), int(read_included), notes, json.dumps(red_flags), time.time()),
        )
    return qid


def list_quotes(spec_id: str):
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM quotes WHERE spec_id=? ORDER BY created_at", (spec_id,)
        ).fetchall()
    out = []
    for r in _rows(rows):
        r["line_items"] = json.loads(r.pop("line_items_json") or "[]")
        r["red_flags"] = json.loads(r.pop("red_flags_json") or "[]")
        out.append(r)
    return out


# ---- outcomes ----

def save_outcome(spec_id: str, facility_name: str, outcome_type: str,
                 details: str, red_flags: list) -> str:
    oid = uuid.uuid4().hex[:8]
    with _conn() as c:
        c.execute(
            """INSERT INTO outcomes (id, spec_id, facility_name, outcome_type, details,
               red_flags_json, created_at) VALUES (?,?,?,?,?,?,?)""",
            (oid, spec_id, facility_name, outcome_type, details,
             json.dumps(red_flags), time.time()),
        )
    return oid


def list_outcomes(spec_id: str):
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM outcomes WHERE spec_id=? ORDER BY created_at", (spec_id,)
        ).fetchall()
    out = []
    for r in _rows(rows):
        r["red_flags"] = json.loads(r.pop("red_flags_json") or "[]")
        out.append(r)
    return out
