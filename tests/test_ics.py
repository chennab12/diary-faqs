"""The .ics export follows RFC 5545 closely enough for Google, Apple and Outlook."""
from datetime import datetime

from ics_export import build_ics

NOW = datetime(2026, 10, 18, 12, 0)


def test_timed_all_day_and_alarm():
    ics = build_ics([
        {"id": 1, "title": "Dentist", "kind": "Appointment", "date": "2026-10-20", "start_time": "15:30", "end_time": "", "location": "Bright Smiles, Suite 2", "notes": ""},
        {"id": 2, "title": "Registration due", "kind": "Deadline", "date": "2026-10-31", "start_time": "", "end_time": "", "location": "", "notes": ""},
    ], now=NOW)
    assert ics.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0") and ics.endswith("END:VCALENDAR\r\n")
    assert "DTSTART:20261020T153000\r\nDTEND:20261020T163000" in ics
    assert "DTSTART;VALUE=DATE:20261031\r\nDTEND;VALUE=DATE:20261101" in ics
    assert "LOCATION:Bright Smiles\\, Suite 2" in ics
    assert ics.count("BEGIN:VEVENT") == 2 and ics.count("BEGIN:VALARM") == 2 and "TRIGGER:-P1D" in ics


def test_end_before_start_is_fixed():
    ics = build_ics([{"id": 1, "title": "x", "kind": "Event", "date": "2026-10-20", "start_time": "15:00", "end_time": "14:00"}], now=NOW)
    assert "DTEND:20261020T160000" in ics


def test_tasks_become_todos_and_long_lines_fold():
    long_title = "Plan the 🎉 birthday party; invite everyone, " * 4
    ics = build_ics([], [{"id": 7, "title": long_title, "due_date": "2026-10-23", "priority": "High", "owner": "Raj", "status": "In progress", "done": 0, "notes": ""}], now=NOW)
    assert "BEGIN:VTODO" in ics and "DUE;VALUE=DATE:20261023" in ics and "PRIORITY:1" in ics and "STATUS:IN-PROCESS" in ics
    for line in ics.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75
    assert "\\;" in ics.replace("\r\n ", "")
