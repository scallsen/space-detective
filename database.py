"""
database.py — Space Detective
Handles SQLite setup, story data ingestion from Story/*.md files,
character-filtered log access, and agent tool-call function implementations.
"""

import sqlite3
import re
import os
from pathlib import Path
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent
STORY_DIR = BASE_DIR / "Story"
DB_PATH   = BASE_DIR / "game.db"

# ── Role IDs (match exactly how the logs are written) ─────────────────────────
ROLES = ["Security Guard", "Chief Engineer", "Botanist", "Technician"]

# Maps role name → character file → is_guilty flag
CHARACTER_META = {
    "Security Guard": {"file": "Security Guard.md", "is_guilty": 1},
    "Chief Engineer": {"file": "Chief Engineer.md", "is_guilty": 0},
    "Botanist":       {"file": "Botanist.md",       "is_guilty": 0},
    "Technician":     {"file": "Technician.md",      "is_guilty": 0},
}


# ══════════════════════════════════════════════════════════════════════════════
# SCHEMA
# ══════════════════════════════════════════════════════════════════════════════

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS characters (
    role        TEXT PRIMARY KEY,   -- "Security Guard" | "Chief Engineer" | ...
    personality TEXT NOT NULL,      -- contents of their Story/*.md file
    is_guilty   INTEGER DEFAULT 0   -- GM-only flag; never exposed to agents
);

CREATE TABLE IF NOT EXISTS scenario (
    id      INTEGER PRIMARY KEY DEFAULT 1,
    summary TEXT NOT NULL           -- contents of Scenario.md
);

CREATE TABLE IF NOT EXISTS incident_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,      -- "04:00"
    person      TEXT NOT NULL,      -- role that performed the action
    action      TEXT NOT NULL,      -- what they did
    visibility  TEXT NOT NULL,      -- "alone" | "was with X" | "was with X and Y"
    sector      TEXT,               -- extracted sector if mentioned
    log_type    TEXT DEFAULT 'action'
    -- 'action'  = character did something
    -- 'witness' = character saw someone else do something
);

CREATE TABLE IF NOT EXISTS character_log_access (
    role    TEXT NOT NULL REFERENCES characters(role),
    log_id  INTEGER NOT NULL REFERENCES incident_logs(id),
    PRIMARY KEY (role, log_id)
);

CREATE TABLE IF NOT EXISTS conversation_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    role         TEXT NOT NULL REFERENCES characters(role),
    speaker      TEXT NOT NULL,     -- 'user' | 'model'
    content      TEXT NOT NULL,
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS game_state (
    id              INTEGER PRIMARY KEY DEFAULT 1,
    oxygen_level    INTEGER DEFAULT 100,
    turns_remaining INTEGER DEFAULT 10,
    game_over       INTEGER DEFAULT 0,
    winner          TEXT
);
"""


# ══════════════════════════════════════════════════════════════════════════════
# CONNECTION HELPER
# ══════════════════════════════════════════════════════════════════════════════

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row       # rows behave like dicts
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ══════════════════════════════════════════════════════════════════════════════
# SEEDING — parse Story/*.md and insert rows
# ══════════════════════════════════════════════════════════════════════════════

def _extract_sector(text: str) -> Optional[str]:
    """Pull 'Sector N' from an action string, or None."""
    m = re.search(r"Sector\s+(\d+)", text, re.IGNORECASE)
    return f"Sector {m.group(1)}" if m else None


def _parse_witnesses(visibility: str) -> list[str]:
    """
    'was with Technician and Chief Engineer'  →  ['Technician', 'Chief Engineer']
    'alone'                                   →  []
    """
    if visibility.strip().lower() == "alone":
        return []
    # Strip leading "was with"
    raw = re.sub(r"^was\s+with\s+", "", visibility.strip(), flags=re.IGNORECASE)
    # Split on " and " or ","
    parts = re.split(r"\s+and\s+|,\s*", raw)
    return [p.strip() for p in parts if p.strip()]


def _parse_log_line(line: str) -> Optional[dict]:
    """
    '[04:01][Botanist][Inspected UV grow-lamps][alone]'
    → {'timestamp': '04:01', 'person': 'Botanist',
       'action': 'Inspected UV grow-lamps', 'visibility': 'alone',
       'sector': None}
    """
    m = re.fullmatch(r"\[([^\]]+)\]\[([^\]]+)\]\[([^\]]+)\]\[([^\]]+)\]", line.strip())
    if not m:
        return None
    timestamp, person, action, visibility = m.groups()
    # Classify witness vs action
    log_type = "witness" if person.lower().startswith("saw ") or "saw " in action[:4] else "action"
    return {
        "timestamp":  timestamp,
        "person":     person,
        "action":     action,
        "visibility": visibility,
        "sector":     _extract_sector(action),
        "log_type":   log_type,
    }


def seed_database(force: bool = False):
    """
    Reads Story/*.md files and populates the database.
    Set force=True to wipe and re-seed (useful during development).
    """
    conn = get_connection()
    cur  = conn.cursor()

    # Create tables. Use executescript so semicolons inside SQL comments do not
    # accidentally split the schema into invalid fragments.
    cur.executescript(SCHEMA_SQL)

    # Skip seeding if data already exists (unless forced)
    if not force:
        cur.execute("SELECT COUNT(*) FROM incident_logs")
        if cur.fetchone()[0] > 0:
            conn.commit()
            conn.close()
            print("[DB] Already seeded - skipping. Pass force=True to re-seed.")
            return

    # Wipe existing data if forced
    if force:
        for table in ["character_log_access", "incident_logs",
                      "conversation_history", "game_state",
                      "characters", "scenario"]:
            cur.execute(f"DELETE FROM {table}")

    # ── 1. Scenario ──────────────────────────────────────────────
    scenario_path = STORY_DIR / "Scenario.md"
    scenario_text = scenario_path.read_text(encoding="utf-8").strip()
    cur.execute(
        "INSERT OR REPLACE INTO scenario (id, summary) VALUES (1, ?)",
        (scenario_text,)
    )
    print("[DB] Scenario loaded.")

    # ── 2. Characters ────────────────────────────────────────────
    for role, meta in CHARACTER_META.items():
        char_path = STORY_DIR / meta["file"]
        personality = char_path.read_text(encoding="utf-8").strip()
        cur.execute(
            "INSERT OR REPLACE INTO characters (role, personality, is_guilty) VALUES (?,?,?)",
            (role, personality, meta["is_guilty"])
        )
    print(f"[DB] {len(CHARACTER_META)} characters loaded.")

    # ── 3. Incident Logs ─────────────────────────────────────────
    logs_path = STORY_DIR / "IncidentLogs.md"
    log_lines = logs_path.read_text(encoding="utf-8").splitlines()

    inserted_logs = []
    for line in log_lines:
        line = line.strip()
        if not line:
            continue
        parsed = _parse_log_line(line)
        if not parsed:
            print(f"[DB] WARNING: Could not parse log line: {line!r}")
            continue
        cur.execute(
            """INSERT INTO incident_logs
               (timestamp, person, action, visibility, sector, log_type)
               VALUES (?,?,?,?,?,?)""",
            (parsed["timestamp"], parsed["person"], parsed["action"],
             parsed["visibility"], parsed["sector"], parsed["log_type"])
        )
        inserted_logs.append((cur.lastrowid, parsed))

    print(f"[DB] {len(inserted_logs)} log entries inserted.")

    # ── 4. Character Log Access ──────────────────────────────────
    # Rule: a character can read a log if they ARE the person
    #       OR they are named in the visibility field.
    access_rows = []
    for log_id, parsed in inserted_logs:
        visible_to = {parsed["person"]}          # always sees own logs
        for witness in _parse_witnesses(parsed["visibility"]):
            visible_to.add(witness)
        for role in visible_to:
            if role in CHARACTER_META:            # only known roles
                access_rows.append((role, log_id))

    cur.executemany(
        "INSERT OR IGNORE INTO character_log_access (role, log_id) VALUES (?,?)",
        access_rows
    )
    print(f"[DB] {len(access_rows)} character-log access rows computed.")

    # ── 5. Initial game state ────────────────────────────────────
    cur.execute(
        """INSERT OR REPLACE INTO game_state
           (id, oxygen_level, turns_remaining, game_over, winner)
           VALUES (1, 100, 10, 0, NULL)"""
    )

    conn.commit()
    conn.close()
    print("[DB] Seeding complete.")


# ══════════════════════════════════════════════════════════════════════════════
# AGENT TOOL FUNCTIONS
# Each function is callable by an agent during its turn.
# Every function takes `role` as its first argument so the DB enforces
# character-level visibility — an agent can NEVER read another agent's
# restricted data.
# ══════════════════════════════════════════════════════════════════════════════

def get_my_personality(role: str) -> dict:
    """
    Returns this character's personality description and role details.
    Agents call this once at session start to know who they are.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT role, personality FROM characters WHERE role = ?", (role,)
    ).fetchone()
    conn.close()
    if not row:
        return {"error": f"Unknown role: {role}"}
    return {"role": row["role"], "personality": row["personality"]}


def get_scenario() -> dict:
    """
    Returns the global mission scenario context.
    All agents can call this — it's public information.
    """
    conn = get_connection()
    row = conn.execute("SELECT summary FROM scenario WHERE id = 1").fetchone()
    conn.close()
    return {"scenario": row["summary"] if row else ""}


def get_my_logs(
    role: str,
    timestamp: Optional[str] = None,
    sector: Optional[str] = None,
    log_type: Optional[str] = None,
    keyword: Optional[str] = None,
) -> dict:
    """
    Returns all log entries this character is authorised to see,
    with optional filters.

    Args:
        role:       The calling agent's role (enforces visibility).
        timestamp:  Filter to a specific time e.g. "04:15".
        sector:     Filter to a specific sector e.g. "Sector 7".
        log_type:   "action" = things they did,
                    "witness" = things they saw others do.
        keyword:    Free-text substring search on the action field.

    Returns:
        {"logs": [{"id", "timestamp", "person", "action", "visibility",
                   "sector", "log_type"}, ...]}
    """
    conn = get_connection()
    query = """
        SELECT il.id, il.timestamp, il.person, il.action,
               il.visibility, il.sector, il.log_type
        FROM   incident_logs il
        JOIN   character_log_access cla ON il.id = cla.log_id
        WHERE  cla.role = ?
    """
    params: list = [role]

    if timestamp:
        query += " AND il.timestamp = ?"
        params.append(timestamp)
    if sector:
        query += " AND il.sector = ?"
        params.append(sector)
    if log_type:
        query += " AND il.log_type = ?"
        params.append(log_type)
    if keyword:
        query += " AND il.action LIKE ?"
        params.append(f"%{keyword}%")

    query += " ORDER BY il.timestamp, il.id"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return {"logs": [dict(r) for r in rows]}


def get_alibi(role: str, suspect_role: str) -> dict:
    """
    Returns all log entries where suspect_role appears —
    but only entries that this character (role) is authorised to see.
    Use this to investigate what another suspect was doing.

    Args:
        role:          The calling agent's role (enforces their visibility).
        suspect_role:  The role to look up e.g. "Security Guard".

    Returns:
        {"alibi_logs": [...], "suspect": suspect_role}
    """
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT il.id, il.timestamp, il.person, il.action,
               il.visibility, il.sector, il.log_type
        FROM   incident_logs il
        JOIN   character_log_access cla ON il.id = cla.log_id
        WHERE  cla.role = ?
          AND  (il.person = ?
                OR il.visibility LIKE ?)
        ORDER  BY il.timestamp, il.id
        """,
        (role, suspect_role, f"%{suspect_role}%")
    ).fetchall()
    conn.close()
    return {
        "suspect":    suspect_role,
        "alibi_logs": [dict(r) for r in rows],
    }


def get_logs_in_time_range(
    role: str,
    start_time: str,
    end_time: str,
) -> dict:
    """
    Returns all logs visible to this character between two timestamps.

    Args:
        role:       The calling agent's role.
        start_time: Inclusive start e.g. "04:10".
        end_time:   Inclusive end   e.g. "04:20".

    Returns:
        {"logs": [...]}
    """
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT il.id, il.timestamp, il.person, il.action,
               il.visibility, il.sector, il.log_type
        FROM   incident_logs il
        JOIN   character_log_access cla ON il.id = cla.log_id
        WHERE  cla.role = ?
          AND  il.timestamp >= ?
          AND  il.timestamp <= ?
        ORDER  BY il.timestamp, il.id
        """,
        (role, start_time, end_time)
    ).fetchall()
    conn.close()
    return {"logs": [dict(r) for r in rows]}


def get_who_was_with_me(role: str, timestamp: Optional[str] = None) -> dict:
    """
    Returns all log entries where this character was with someone else —
    their shared alibi entries. Optionally filter by timestamp.

    Args:
        role:       The calling agent's role.
        timestamp:  Optional specific minute e.g. "04:05".

    Returns:
        {"shared_logs": [...]}
    """
    conn = get_connection()
    query = """
        SELECT il.id, il.timestamp, il.person, il.action,
               il.visibility, il.sector
        FROM   incident_logs il
        JOIN   character_log_access cla ON il.id = cla.log_id
        WHERE  cla.role = ?
          AND  il.visibility != 'alone'
          AND  il.visibility LIKE ?
    """
    params: list = [role, f"%{role}%"]

    if timestamp:
        query += " AND il.timestamp = ?"
        params.append(timestamp)

    query += " ORDER BY il.timestamp, il.id"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return {"shared_logs": [dict(r) for r in rows]}


def search_logs(role: str, keyword: str) -> dict:
    """
    Free-text keyword search across all log entries visible to this character.

    Args:
        role:    The calling agent's role.
        keyword: Word or phrase to search in the action text.

    Returns:
        {"results": [...], "keyword": keyword}
    """
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT il.id, il.timestamp, il.person, il.action,
               il.visibility, il.sector, il.log_type
        FROM   incident_logs il
        JOIN   character_log_access cla ON il.id = cla.log_id
        WHERE  cla.role = ?
          AND  il.action LIKE ?
        ORDER  BY il.timestamp, il.id
        """,
        (role, f"%{keyword}%")
    ).fetchall()
    conn.close()
    return {"keyword": keyword, "results": [dict(r) for r in rows]}


# ── Conversation Memory ────────────────────────────────────────────────────────

def append_conversation(role: str, speaker: str, content: str):
    """Persist a turn in this agent's conversation history."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO conversation_history (role, speaker, content) VALUES (?,?,?)",
        (role, speaker, content)
    )
    conn.commit()
    conn.close()


def get_conversation_history(role: str, last_n: int = 20) -> list[dict]:
    """Retrieve the last N turns for this agent."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT speaker, content FROM conversation_history
           WHERE role = ?
           ORDER BY id DESC
           LIMIT ?""",
        (role, last_n)
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


# ── Game State ─────────────────────────────────────────────────────────────────

def get_game_state() -> dict:
    conn = get_connection()
    row = conn.execute("SELECT * FROM game_state WHERE id = 1").fetchone()
    conn.close()
    return dict(row) if row else {}


def update_game_state(oxygen_level: int = None, turns_remaining: int = None,
                      game_over: bool = None, winner: str = None):
    conn = get_connection()
    updates, params = [], []
    if oxygen_level    is not None: updates.append("oxygen_level = ?");    params.append(oxygen_level)
    if turns_remaining is not None: updates.append("turns_remaining = ?"); params.append(turns_remaining)
    if game_over       is not None: updates.append("game_over = ?");       params.append(int(game_over))
    if winner          is not None: updates.append("winner = ?");          params.append(winner)
    if updates:
        conn.execute(f"UPDATE game_state SET {', '.join(updates)} WHERE id = 1", params)
        conn.commit()
    conn.close()


def reset_game():
    """Wipe conversation history and reset game state to fresh start."""
    conn = get_connection()
    conn.execute("DELETE FROM conversation_history")
    conn.execute(
        "UPDATE game_state SET oxygen_level=100, turns_remaining=10, game_over=0, winner=NULL WHERE id=1"
    )
    conn.commit()
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# GEMINI TOOL DECLARATIONS
# These JSON schemas are passed to the Gemini API as function_declarations.
# Each agent receives only its own role-scoped tool set.
# ══════════════════════════════════════════════════════════════════════════════

def build_agent_tools(role: str) -> list[dict]:
    """
    Returns the list of Gemini-compatible function declarations for a given role.
    The `role` is baked into each tool's description so the agent knows
    it is always calling on its own data only.
    """
    return [
        {
            "name": "get_my_logs",
            "description": (
                f"Retrieve activity logs that {role} is authorised to see. "
                "Filter by timestamp (e.g. '04:15'), sector (e.g. 'Sector 7'), "
                "log_type ('action' for things you did, 'witness' for things you saw), "
                "or a keyword in the action text."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "timestamp": {
                        "type": "string",
                        "description": "Exact minute to filter, e.g. '04:15'"
                    },
                    "sector": {
                        "type": "string",
                        "description": "Sector name to filter, e.g. 'Sector 7'"
                    },
                    "log_type": {
                        "type": "string",
                        "enum": ["action", "witness"],
                        "description": "'action' = things I did. 'witness' = things I saw others do."
                    },
                    "keyword": {
                        "type": "string",
                        "description": "Word or phrase to search in the action text."
                    }
                }
            }
        },
        {
            "name": "get_alibi",
            "description": (
                f"Look up what another suspect was doing during the incident, "
                f"filtered to only what {role} personally witnessed or was present for. "
                "Use this when asked about another crew member's whereabouts."
            ),
            "parameters": {
                "type": "object",
                "required": ["suspect_role"],
                "properties": {
                    "suspect_role": {
                        "type": "string",
                        "enum": ["Security Guard", "Chief Engineer", "Botanist", "Technician"],
                        "description": "The role of the crew member to look up."
                    }
                }
            }
        },
        {
            "name": "get_logs_in_time_range",
            "description": (
                f"Get all logs visible to {role} between two timestamps. "
                "Useful for reconstructing what happened during a specific window."
            ),
            "parameters": {
                "type": "object",
                "required": ["start_time", "end_time"],
                "properties": {
                    "start_time": {
                        "type": "string",
                        "description": "Start of the time range, e.g. '04:10'"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End of the time range, e.g. '04:20'"
                    }
                }
            }
        },
        {
            "name": "get_who_was_with_me",
            "description": (
                f"Returns all log entries where {role} was not alone — "
                "i.e. their shared alibi moments with other crew members. "
                "Optionally filter to a specific minute."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "timestamp": {
                        "type": "string",
                        "description": "Optional specific minute, e.g. '04:05'"
                    }
                }
            }
        },
        {
            "name": "search_logs",
            "description": (
                f"Free-text search across all logs visible to {role}. "
                "Returns any log entry whose action text contains the keyword."
            ),
            "parameters": {
                "type": "object",
                "required": ["keyword"],
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Word or phrase to search, e.g. 'oxygen', 'alarm', 'Sector 7'"
                    }
                }
            }
        },
    ]


# ══════════════════════════════════════════════════════════════════════════════
# TOOL DISPATCHER
# Receives a function_call from the Gemini agent and routes it to the
# correct Python function, always injecting the agent's role.
# ══════════════════════════════════════════════════════════════════════════════

def dispatch_tool_call(role: str, function_name: str, args: dict) -> dict:
    """
    Called by server.py when the Gemini agent returns a function_call.
    Injects `role` automatically — agents cannot override this.
    """
    args_with_role = {"role": role, **args}

    dispatch = {
        "get_my_logs":           get_my_logs,
        "get_alibi":             get_alibi,
        "get_logs_in_time_range": get_logs_in_time_range,
        "get_who_was_with_me":   get_who_was_with_me,
        "search_logs":           search_logs,
    }

    fn = dispatch.get(function_name)
    if not fn:
        return {"error": f"Unknown tool: {function_name}"}

    try:
        return fn(**args_with_role)
    except TypeError as e:
        return {"error": f"Bad arguments for {function_name}: {e}"}


# ══════════════════════════════════════════════════════════════════════════════
# CLI — run directly to seed the DB
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    seed_database(force=force)

    # Quick sanity check
    print("\n-- Sanity checks -----------------------------------------")
    result = get_my_logs("Security Guard")
    print(f"Security Guard can see {len(result['logs'])} log entries.")

    result = get_alibi("Chief Engineer", "Security Guard")
    print(f"Chief Engineer knows {len(result['alibi_logs'])} logs about Security Guard.")

    result = get_logs_in_time_range("Botanist", "04:14", "04:16")
    print(f"Botanist logs 04:14-04:16: {len(result['logs'])} entries.")
    for l in result["logs"]:
        print(f"  [{l['timestamp']}] {l['person']}: {l['action']}")

    result = get_who_was_with_me("Chief Engineer")
    print(f"Chief Engineer shared alibi entries: {len(result['shared_logs'])}")
