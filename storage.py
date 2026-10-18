"""Local SQLite storage for journal entries, tasks, calendar events and ideas."""
import json
import os
import sqlite3
from datetime import date, datetime

STATUSES = ["To do", "In progress", "Waiting", "Done"]
PRIORITIES = ["High", "Medium", "Low"]
EVENT_KINDS = ["Event", "Appointment", "Deadline", "Reminder"]
DEFAULT_OWNER = "Me"

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    body TEXT NOT NULL,
    summary TEXT DEFAULT '',
    mood TEXT DEFAULT '',
    mood_score INTEGER DEFAULT 0,
    tags TEXT DEFAULT '[]',
    reflection TEXT DEFAULT '',
    engine TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER,
    title TEXT NOT NULL,
    owner TEXT DEFAULT 'Me',
    status TEXT DEFAULT 'To do',
    done INTEGER DEFAULT 0,
    due_date TEXT DEFAULT '',
    priority TEXT DEFAULT 'Medium',
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    completed_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER,
    title TEXT NOT NULL,
    kind TEXT DEFAULT 'Event',
    date TEXT NOT NULL,
    start_time TEXT DEFAULT '',
    end_time TEXT DEFAULT '',
    location TEXT DEFAULT '',
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def default_path():
    """DIARY_DB overrides the database file; otherwise diary.db sits next to the app."""
    return os.environ.get("DIARY_DB") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "diary.db")


def _now():
    return datetime.now().isoformat(timespec="seconds")


def sync_status(status, done):
    """Keep the checkbox and the status column in agreement; the checkbox wins when they disagree."""
    if done:
        return "Done", 1
    if status == "Done":
        return "To do", 0
    return (status if status in STATUSES else "To do"), 0


class Store:
    def __init__(self, path=None):
        self.path = path or default_path()
        with self._conn() as con:
            con.executescript(SCHEMA)

    def _conn(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def _rows(self, sql, args=()):
        with self._conn() as con:
            return [dict(r) for r in con.execute(sql, args).fetchall()]

    # Entries
    def add_entry(self, body, entry_date, analysis=None):
        a = analysis or {}
        with self._conn() as con:
            cur = con.execute(
                "INSERT INTO entries (entry_date, created_at, body, summary, mood, mood_score, tags, reflection, engine)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    str(entry_date), _now(), body, a.get("summary", ""), a.get("mood", ""), int(a.get("mood_score", 0)),
                    json.dumps(a.get("tags", [])), a.get("reflection", ""), a.get("engine", ""),
                ),
            )
            return cur.lastrowid

    def update_entry_analysis(self, entry_id, analysis):
        with self._conn() as con:
            con.execute(
                "UPDATE entries SET summary=?, mood=?, mood_score=?, tags=?, reflection=?, engine=? WHERE id=?",
                (
                    analysis.get("summary", ""), analysis.get("mood", ""), int(analysis.get("mood_score", 0)),
                    json.dumps(analysis.get("tags", [])), analysis.get("reflection", ""), analysis.get("engine", ""), entry_id,
                ),
            )

    def entries(self, search=""):
        rows = self._rows("SELECT * FROM entries ORDER BY entry_date DESC, id DESC")
        for r in rows:
            r["tags"] = json.loads(r["tags"] or "[]")
        if search:
            s = search.lower()
            rows = [r for r in rows if s in r["body"].lower() or s in r["summary"].lower() or any(s in t.lower() for t in r["tags"])]
        return rows

    def delete_entry(self, entry_id, with_actions=False):
        with self._conn() as con:
            con.execute("DELETE FROM entries WHERE id=?", (entry_id,))
            for table in ("tasks", "events", "ideas"):
                if with_actions:
                    con.execute(f"DELETE FROM {table} WHERE entry_id=?", (entry_id,))
                else:
                    con.execute(f"UPDATE {table} SET entry_id=NULL WHERE entry_id=?", (entry_id,))

    # Tasks
    def add_task(self, title, owner=DEFAULT_OWNER, due_date="", priority="Medium", notes="", entry_id=None, status="To do"):
        status, done = sync_status(status, status == "Done")
        with self._conn() as con:
            cur = con.execute(
                "INSERT INTO tasks (entry_id, title, owner, status, done, due_date, priority, notes, created_at, completed_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (entry_id, title.strip(), (owner or DEFAULT_OWNER).strip(), status, done, str(due_date or ""),
                 priority if priority in PRIORITIES else "Medium", notes, _now(), _now() if done else ""),
            )
            return cur.lastrowid

    def tasks(self):
        return self._rows("SELECT * FROM tasks ORDER BY done, CASE WHEN due_date='' THEN 1 ELSE 0 END, due_date, id")

    def update_task(self, task_id, **fields):
        current = self._rows("SELECT * FROM tasks WHERE id=?", (task_id,))
        if not current:
            return
        row = {**current[0], **fields}
        if "done" in fields and "status" not in fields:
            row["status"] = "Done" if fields["done"] else ("To do" if current[0]["status"] == "Done" else current[0]["status"])
        elif "status" in fields and "done" not in fields:
            row["done"] = 1 if fields["status"] == "Done" else 0
        row["status"], row["done"] = sync_status(row["status"], bool(row["done"]))
        if row["done"] and not current[0]["done"]:
            row["completed_at"] = _now()
        elif not row["done"]:
            row["completed_at"] = ""
        with self._conn() as con:
            con.execute(
                "UPDATE tasks SET title=?, owner=?, status=?, done=?, due_date=?, priority=?, notes=?, completed_at=? WHERE id=?",
                (row["title"], row["owner"] or DEFAULT_OWNER, row["status"], row["done"], str(row["due_date"] or ""),
                 row["priority"], row["notes"] or "", row["completed_at"], task_id),
            )

    def delete_task(self, task_id):
        with self._conn() as con:
            con.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    # Events
    def add_event(self, title, event_date, kind="Event", start_time="", end_time="", location="", notes="", entry_id=None):
        with self._conn() as con:
            cur = con.execute(
                "INSERT INTO events (entry_id, title, kind, date, start_time, end_time, location, notes) VALUES (?,?,?,?,?,?,?,?)",
                (entry_id, title.strip(), kind if kind in EVENT_KINDS else "Event", str(event_date), start_time or "",
                 end_time or "", location or "", notes or ""),
            )
            return cur.lastrowid

    def events(self, start=None, end=None):
        rows = self._rows("SELECT * FROM events ORDER BY date, CASE WHEN start_time='' THEN 0 ELSE 1 END, start_time, id")
        if start:
            rows = [r for r in rows if r["date"] >= str(start)]
        if end:
            rows = [r for r in rows if r["date"] <= str(end)]
        return rows

    def update_event(self, event_id, **fields):
        allowed = ["title", "kind", "date", "start_time", "end_time", "location", "notes"]
        sets = [(k, str(v) if k == "date" else (v or "")) for k, v in fields.items() if k in allowed]
        if not sets:
            return
        with self._conn() as con:
            con.execute(f"UPDATE events SET {', '.join(k + '=?' for k, _ in sets)} WHERE id=?", [v for _, v in sets] + [event_id])

    def delete_event(self, event_id):
        with self._conn() as con:
            con.execute("DELETE FROM events WHERE id=?", (event_id,))

    # Ideas
    def add_idea(self, text, entry_id=None):
        with self._conn() as con:
            return con.execute("INSERT INTO ideas (entry_id, text, created_at) VALUES (?,?,?)", (entry_id, text.strip(), _now())).lastrowid

    def ideas(self):
        return self._rows("SELECT * FROM ideas ORDER BY id DESC")

    def delete_idea(self, idea_id):
        with self._conn() as con:
            con.execute("DELETE FROM ideas WHERE id=?", (idea_id,))

    # Saving an analyzed entry in one step
    def save_analysis(self, body, entry_date, analysis, tasks=None, events=None, ideas=None):
        """Store the entry plus the actions the user kept; returns the new entry id."""
        entry_id = self.add_entry(body, entry_date, analysis)
        for t in analysis.get("tasks", []) if tasks is None else tasks:
            self.add_task(t["title"], t.get("owner") or DEFAULT_OWNER, t.get("due_date", ""), t.get("priority", "Medium"), t.get("notes", ""), entry_id)
        for e in analysis.get("events", []) if events is None else events:
            self.add_event(e["title"], e["date"], e.get("kind", "Event"), e.get("start_time", ""), e.get("end_time", ""), e.get("location", ""), e.get("notes", ""), entry_id)
        for i in analysis.get("ideas", []) if ideas is None else ideas:
            self.add_idea(i, entry_id)
        return entry_id

    # Backup
    def export_json(self):
        return json.dumps(
            {"version": 1, "exported": _now(), "entries": self.entries(), "tasks": self.tasks(), "events": self.events(), "ideas": self.ideas()},
            indent=2,
        )

    def import_json(self, text):
        """Add everything from a backup; old entry ids are remapped so links between entries and actions survive."""
        data = json.loads(text)
        id_map = {}
        for e in data.get("entries", []):
            id_map[e["id"]] = self.add_entry(e["body"], e["entry_date"], e)
        for t in data.get("tasks", []):
            new = self.add_task(t["title"], t.get("owner", DEFAULT_OWNER), t.get("due_date", ""), t.get("priority", "Medium"), t.get("notes", ""), id_map.get(t.get("entry_id")), t.get("status", "To do"))
            if t.get("done"):
                self.update_task(new, done=1)
        for ev in data.get("events", []):
            self.add_event(ev["title"], ev["date"], ev.get("kind", "Event"), ev.get("start_time", ""), ev.get("end_time", ""), ev.get("location", ""), ev.get("notes", ""), id_map.get(ev.get("entry_id")))
        for i in data.get("ideas", []):
            self.add_idea(i["text"], id_map.get(i.get("entry_id")))
        return len(data.get("entries", [])), len(data.get("tasks", [])), len(data.get("events", []))

    def journal_streak(self, today=None):
        """Consecutive days with at least one entry, ending today (or yesterday if today has none yet)."""
        today = today or date.today()
        days = {r["entry_date"] for r in self._rows("SELECT entry_date FROM entries")}
        d = today if str(today) in days else date.fromordinal(today.toordinal() - 1)
        streak = 0
        while str(d) in days:
            streak += 1
            d = date.fromordinal(d.toordinal() - 1)
        return streak
