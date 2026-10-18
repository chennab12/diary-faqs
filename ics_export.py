"""Build an iCalendar (.ics) file that Google, Apple and Outlook calendars can import."""
from datetime import date, datetime, timedelta, timezone

PRODID = "-//diary-faqs//Diary Actions//EN"


def _escape(text):
    return str(text or "").replace("\\", "\\\\").replace(";", "\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def _fold(line):
    """RFC 5545 lines are at most 75 octets; longer ones continue on lines starting with a space."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, current = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(current) + len(b) > (75 if not parts else 74):
            parts.append(current.decode("utf-8"))
            current = b""
        current += b
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def _dt(day, hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, m)


def event_lines(item, uid, stamp):
    day = date.fromisoformat(item["date"])
    lines = ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}"]
    if item.get("start_time"):
        start = _dt(day, item["start_time"])
        end = _dt(day, item["end_time"]) if item.get("end_time") else start + timedelta(hours=1)
        if end <= start:
            end = start + timedelta(hours=1)
        lines += [f"DTSTART:{start:%Y%m%dT%H%M%S}", f"DTEND:{end:%Y%m%dT%H%M%S}"]
    else:
        lines += [f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}"]
    kind = item.get("kind", "Event")
    lines.append(f"SUMMARY:{_escape(item['title'])}")
    if item.get("location"):
        lines.append(f"LOCATION:{_escape(item['location'])}")
    notes = " · ".join(x for x in [kind, item.get("notes", "")] if x)
    lines += [f"DESCRIPTION:{_escape(notes)}", f"CATEGORIES:{_escape(kind)}"]
    if kind in ("Deadline", "Reminder", "Appointment"):
        trigger = "-P1D" if kind == "Deadline" else "-PT30M"
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_escape(item['title'])}", f"TRIGGER:{trigger}", "END:VALARM"]
    lines.append("END:VEVENT")
    return lines


def task_lines(task, uid, stamp):
    """Open tasks become VTODO items, which Apple Reminders and Outlook tasks understand."""
    lines = ["BEGIN:VTODO", f"UID:{uid}", f"DTSTAMP:{stamp}", f"SUMMARY:{_escape(task['title'])}"]
    if task.get("due_date"):
        lines.append(f"DUE;VALUE=DATE:{date.fromisoformat(task['due_date']):%Y%m%d}")
    lines.append(f"PRIORITY:{ {'High': 1, 'Medium': 5, 'Low': 9}.get(task.get('priority'), 5) }")
    status = "COMPLETED" if task.get("done") else "IN-PROCESS" if task.get("status") == "In progress" else "NEEDS-ACTION"
    lines.append(f"STATUS:{status}")
    lines.append(f"DESCRIPTION:{_escape('Owner: ' + (task.get('owner') or 'Me') + ('. ' + task['notes'] if task.get('notes') else ''))}")
    lines.append("END:VTODO")
    return lines


def build_ics(events, tasks=(), now=None):
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Diary actions"]
    for e in events:
        lines += event_lines(e, f"event-{e.get('id', id(e))}-{e['date']}@diary-faqs", stamp)
    for t in tasks:
        lines += task_lines(t, f"task-{t.get('id', id(t))}@diary-faqs", stamp)
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
