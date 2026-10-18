"""SQLite storage: tasks keep checkbox and status in sync, and backups round-trip."""
from datetime import date

from storage import Store, sync_status


def test_sync_status():
    assert sync_status("In progress", True) == ("Done", 1)
    assert sync_status("Done", False) == ("To do", 0)
    assert sync_status("Waiting", False) == ("Waiting", 0)
    assert sync_status("nonsense", False) == ("To do", 0)


def test_checkbox_and_status_stay_in_sync(isolated):
    s = Store()
    tid = s.add_task("Call mom", due_date="2026-10-19")
    s.update_task(tid, done=1)
    t = s.tasks()[0]
    assert t["status"] == "Done" and t["done"] == 1 and t["completed_at"]
    s.update_task(tid, done=0)
    assert s.tasks()[0]["status"] == "To do"
    s.update_task(tid, status="In progress")
    assert s.tasks()[0]["done"] == 0
    s.update_task(tid, status="Done")
    assert s.tasks()[0]["done"] == 1
    s.update_task(tid, owner="Raj", priority="High")
    assert (s.tasks()[0]["owner"], s.tasks()[0]["priority"]) == ("Raj", "High")
    s.delete_task(tid)
    assert s.tasks() == []


def test_save_analysis_links_actions(isolated):
    s = Store()
    analysis = {"summary": "S", "mood": "🙂 Good", "mood_score": 1, "tags": ["work"], "reflection": "", "engine": "rules",
                "tasks": [{"title": "Send deck", "owner": "Raj", "due_date": "2026-10-23", "priority": "High"}],
                "events": [{"title": "Dentist", "date": "2026-10-20", "kind": "Appointment", "start_time": "15:30"}], "ideas": ["Game night"]}
    eid = s.save_analysis("text", date(2026, 10, 18), analysis)
    assert s.tasks()[0]["entry_id"] == eid and s.events()[0]["entry_id"] == eid and s.ideas()[0]["entry_id"] == eid
    assert s.entries()[0]["tags"] == ["work"]
    assert s.entries("work")[0]["id"] == eid and s.entries("zzz") == []
    assert len(s.events("2026-10-21")) == 0 and len(s.events("2026-10-20", "2026-10-20")) == 1
    s.delete_entry(eid)
    assert s.tasks()[0]["entry_id"] is None
    eid2 = s.save_analysis("again", date(2026, 10, 18), analysis)
    s.delete_entry(eid2, with_actions=True)
    assert len(s.tasks()) == 1


def test_backup_round_trip(isolated, tmp_path):
    a = Store()
    eid = a.add_entry("hello", "2026-10-18", {"mood": "🙂 Good", "tags": ["x"]})
    tid = a.add_task("Do it", entry_id=eid)
    a.update_task(tid, done=1)
    a.add_event("Party", "2026-11-02", start_time="14:00", entry_id=eid)
    a.add_idea("Idea", eid)
    b = Store(str(tmp_path / "other.db"))
    assert b.import_json(a.export_json()) == (1, 1, 1)
    new_entry = b.entries()[0]["id"]
    assert b.tasks()[0]["done"] == 1 and b.tasks()[0]["entry_id"] == new_entry
    assert b.events()[0]["start_time"] == "14:00" and b.ideas()[0]["entry_id"] == new_entry


def test_journal_streak(isolated):
    s = Store()
    for d in ["2026-10-15", "2026-10-16", "2026-10-17"]:
        s.add_entry("x", d)
    assert s.journal_streak(date(2026, 10, 18)) == 3
    s.add_entry("x", "2026-10-18")
    assert s.journal_streak(date(2026, 10, 18)) == 4
    assert s.journal_streak(date(2026, 10, 25)) == 0


def test_update_event(isolated):
    s = Store()
    ev = s.add_event("Lunch", "2026-10-20")
    s.update_event(ev, title="Lunch with Ana", date=date(2026, 10, 21), start_time="12:00")
    e = s.events()[0]
    assert (e["title"], e["date"], e["start_time"]) == ("Lunch with Ana", "2026-10-21", "12:00")
    s.delete_event(ev)
    assert s.events() == []
