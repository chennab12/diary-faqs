"""Turn free-form journal text into a summary, mood, tags, tasks, calendar events and ideas.

Two engines share one output shape:
- "ai": Claude through the Anthropic API (needs ANTHROPIC_API_KEY), best at messy writing.
- "rules": an offline parser for dates, times, task phrases and owners, used when there is no key or the API fails.
"""
import calendar
import json
import os
import re
from datetime import date, timedelta

from storage import DEFAULT_OWNER, EVENT_KINDS, PRIORITIES

MODEL = os.environ.get("DIARY_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("DIARY_EFFORT", "medium")

MOODS = ["😀 Great", "🙂 Good", "😐 Neutral", "😕 Low", "😞 Rough"]

WEEKDAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
}
MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
MONTHS["sept"] = 9
NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

_WD = "|".join(sorted(WEEKDAYS, key=len, reverse=True))
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))
_NUM = r"\d+|" + "|".join(NUMBER_WORDS)

EVENT_WORDS = [
    "appointment", "appt", "meeting", "meet with", "meet up", "call with", "zoom", "dentist", "doctor", "dr.", "checkup", "check-up",
    "physical", "therapy", "lunch", "dinner", "breakfast", "brunch", "coffee with", "party", "wedding", "birthday", "anniversary",
    "flight", "trip", "interview", "class", "lesson", "practice", "game", "recital", "concert", "conference", "webinar", "visit",
    "vet", "haircut", "ceremony", "reunion", "play date", "playdate", "1:1", "one-on-one", "standup", "sync", "demo", "workshop",
    "parent-teacher", "pta", "open house", "show", "movie", "hike", "date night", "service", "game night", "tournament", "event",
]
APPOINTMENT_WORDS = ["appointment", "appt", "dentist", "doctor", "dr.", "checkup", "check-up", "physical", "therapy", "vet", "haircut", "interview"]
DEADLINE_WORDS = ["due", "deadline", "expires", "expire", "submit", "file ", "renew", "pay ", "register", "sign up", "apply", "rsvp", "return"]
REMINDER_WORDS = ["remind me", "reminder"]
TASK_CUES = [
    r"(?:i|we)\s+(?:really\s+)?(?:need|have|got|ought)\s+to", r"(?:i|we)\s+must", r"(?:i|we)\s+should", r"(?:i|we)\s*(?:'ll|will)",
    r"(?:i|we)\s+(?:am|are|'m|'re)\s+going\s+to", r"(?:i|we)\s+plan\s+to", r"need\s+to", r"have\s+to", r"must", r"gotta",
    r"(?:please\s+)?remember\s+to", r"don'?t\s+forget\s+to", r"remind\s+me\s+to", r"to-?do:?", r"todo:?", r"action(?: item)?:",
]
IMPERATIVE_VERBS = [
    "call", "email", "text", "buy", "order", "book", "schedule", "pay", "renew", "fix", "finish", "send", "submit", "file", "clean",
    "pick up", "drop off", "return", "cancel", "update", "review", "prepare", "prep", "write", "plan", "check", "follow up", "sign",
    "register", "apply", "print", "pack", "wash", "mow", "water", "replace", "install", "organize", "research", "read", "practice",
    "study", "draft", "share", "ask", "remind", "confirm", "reply", "respond", "get", "make", "set up", "start", "back up",
]
IDEA_CUES = [r"\bidea\b", r"\bwhat if\b", r"\bmaybe (?:i|we) could\b", r"\bi wonder\b", r"\bit would be (?:nice|cool|great|fun)\b", r"\bsomeday\b", r"\bone day i\b", r"\bi could try\b"]
HIGH_WORDS = ["urgent", "asap", "important", "critical", "high priority", "top priority", "must", "immediately", "overdue"]
LOW_WORDS = ["someday", "eventually", "low priority", "if i have time", "when i get a chance", "no rush", "maybe"]
NOT_NAMES = {"I", "We", "You", "He", "She", "They", "It", "This", "That", "Today", "Tomorrow", "Tonight", "Then", "Also", "And", "But", "So",
             "Maybe", "Need", "Remember", "Please", "Don't", "Dont", "The", "My", "Our", "Next", "Mom", "Dad"} | {d.title() for d in WEEKDAYS} | {m.title() for m in MONTHS}

TAGS = {
    "work": ["work", "meeting", "manager", "project", "deadline", "client", "office", "boss", "team", "review", "standup", "1:1", "promotion", "launch"],
    "family": ["family", "mom", "dad", "wife", "husband", "son", "daughter", "kid", "kids", "parents", "sister", "brother", "grandma", "grandpa", "spouse"],
    "health": ["doctor", "dentist", "gym", "workout", "run", "sleep", "health", "sick", "therapy", "walk", "yoga", "checkup", "medicine", "diet"],
    "money": ["pay", "bill", "budget", "bank", "tax", "taxes", "rent", "invest", "savings", "insurance", "money", "invoice", "mortgage"],
    "home": ["house", "home", "clean", "repair", "garden", "laundry", "groceries", "fix", "plumber", "yard", "kitchen", "garage"],
    "school": ["school", "teacher", "homework", "class", "pta", "recital", "lesson", "tutor", "field trip", "report card"],
    "social": ["friend", "friends", "party", "dinner", "lunch", "coffee", "wedding", "birthday", "game night", "reunion"],
    "travel": ["trip", "flight", "hotel", "vacation", "travel", "airport", "passport", "visa", "packing"],
    "learning": ["learn", "course", "reading", "read a", "study", "practice", "tutorial", "podcast", "skill"],
    "self-care": ["grateful", "gratitude", "meditate", "journal", "relax", "rest", "hobby", "walk", "me time"],
}
POSITIVE = {"happy", "great", "good", "glad", "grateful", "thankful", "excited", "proud", "love", "loved", "calm", "relaxed", "fun",
            "amazing", "awesome", "wonderful", "productive", "energized", "peaceful", "hopeful", "joy", "enjoyed", "win", "won", "better", "nice", "smile", "laughed", "accomplished", "rested"}
NEGATIVE = {"sad", "tired", "stressed", "stress", "anxious", "worried", "angry", "upset", "frustrated", "overwhelmed", "lonely", "bad",
            "awful", "terrible", "sick", "exhausted", "annoyed", "hate", "cried", "fight", "argument", "lost", "fail", "failed", "worse", "behind", "burned", "burnt", "scared", "hurt", "pain"}
NEGATORS = {"not", "no", "never", "isn't", "wasn't", "don't", "didn't", "hardly"}


# ---------- dates and times ----------

def _next_weekday(today, wd, mode):
    ahead = (wd - today.weekday()) % 7
    if mode == "next":
        start_next_week = today + timedelta(days=7 - today.weekday())
        return start_next_week + timedelta(days=wd)
    if ahead == 0 and mode != "this":
        ahead = 7
    return today + timedelta(days=ahead)


def _safe_date(y, m, d):
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _year_for(today, m, d):
    """Dates written without a year mean the next occurrence, unless they were within the last week (a recent past note)."""
    candidate = _safe_date(today.year, m, d)
    if candidate and candidate < today - timedelta(days=7):
        candidate = _safe_date(today.year + 1, m, d)
    return candidate


def _add_months(d, n):
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def find_date(text, today):
    """Return (date, matched phrase) for the first date-like phrase, or (None, '')."""
    t = text.lower()
    rules = [
        (r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", lambda g: _safe_date(int(g[0]), int(g[1]), int(g[2]))),
        (r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", lambda g: _safe_date(int(g[2]) + (2000 if len(g[2]) == 2 else 0), int(g[0]), int(g[1]))),
        (r"\b(\d{1,2})/(\d{1,2})\b", lambda g: _year_for(today, int(g[0]), int(g[1]))),
        (rf"\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b",
         lambda g: _safe_date(int(g[2]), MONTHS[g[0]], int(g[1])) if g[2] else _year_for(today, MONTHS[g[0]], int(g[1]))),
        (rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MON})\b", lambda g: _year_for(today, MONTHS[g[1]], int(g[0]))),
        (r"\bday after tomorrow\b", lambda g: today + timedelta(days=2)),
        (r"\b(?:tomorrow|tmrw|tmr)\b", lambda g: today + timedelta(days=1)),
        (r"\b(?:today|tonight|this (?:morning|afternoon|evening))\b", lambda g: today),
        (rf"\bin\s+({_NUM})\s+(day|days|week|weeks|month|months)\b", lambda g: _in_n(today, g[0], g[1])),
        (r"\b(?:end of (?:the )?month|month[- ]end)\b", lambda g: date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])),
        (r"\b(?:end of (?:the )?week|eow)\b", lambda g: _next_weekday(today, 4, "this")),
        (r"\bthis weekend\b", lambda g: _next_weekday(today, 5, "this")),
        (r"\bnext weekend\b", lambda g: _next_weekday(today, 5, "next")),
        (r"\bnext week\b", lambda g: _next_weekday(today, 0, "next")),
        (r"\bnext month\b", lambda g: _add_months(today.replace(day=1), 1)),
        (rf"\b(next|this|coming|on|by|before|until)?\s*({_WD})\b\.?", lambda g: _next_weekday(today, WEEKDAYS[g[1]], g[0] or "")),
    ]
    best = None
    for pattern, build in rules:
        m = re.search(pattern, t)
        if m:
            d = build(m.groups())
            if d and (best is None or m.start() < best[2]):
                best = (d, text[m.start():m.end()], m.start())
    return (best[0], best[1]) if best else (None, "")


def _in_n(today, n, unit):
    n = NUMBER_WORDS.get(n, None) or int(n)
    if unit.startswith("day"):
        return today + timedelta(days=n)
    if unit.startswith("week"):
        return today + timedelta(weeks=n)
    return _add_months(today, n)


def _hm(h, m, ampm):
    h, m = int(h), int(m or 0)
    if ampm:
        ampm = ampm.replace(".", "")
        if ampm == "pm" and h < 12:
            h += 12
        if ampm == "am" and h == 12:
            h = 0
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return ""
    return f"{h:02d}:{m:02d}"


def find_times(text):
    """Return (start 'HH:MM' or '', end 'HH:MM' or '', matched phrase)."""
    t = text.lower()
    ampm = r"(a\.?m\.?|p\.?m\.?)"
    m = re.search(rf"\b(\d{{1,2}})(?::(\d{{2}}))?\s*{ampm}?\s*(?:-|–|to|until)\s*(\d{{1,2}})(?::(\d{{2}}))?\s*{ampm}", t)
    if m:
        h1, m1, ap1, h2, m2, ap2 = m.groups()
        ap1 = ap1 or ap2
        if not m.group(3) and int(h1) > int(h2) and ap2 and ap2.startswith("p"):
            ap1 = "am"
        return _hm(h1, m1, ap1), _hm(h2, m2, ap2), text[m.start():m.end()]
    m = re.search(rf"\b(\d{{1,2}})(?::(\d{{2}}))?\s*{ampm}", t)
    if m:
        return _hm(m.group(1), m.group(2), m.group(3)), "", text[m.start():m.end()]
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", t)
    if m:
        return _hm(m.group(1), m.group(2), None), "", text[m.start():m.end()]
    m = re.search(r"\b(noon|midday|midnight)\b", t)
    if m:
        return ("00:00" if m.group(1) == "midnight" else "12:00"), "", text[m.start():m.end()]
    m = re.search(r"\bat\s+(\d{1,2})\b(?!\s*(?:/|:|-|\d|st|nd|rd|th|%|people|kids|minutes|mins|hours))", t)
    if m and 1 <= int(m.group(1)) <= 12:
        h = int(m.group(1))
        return _hm(h, 0, "pm" if h <= 7 or h == 12 else "am"), "", text[m.start():m.end()]
    return "", "", ""


# ---------- sentence helpers ----------

def split_sentences(text):
    parts = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)]|\[ ?\])\s*", "", line).strip()
        if not line:
            continue
        parts.extend(s.strip() for s in re.split(r"(?<=[.!?;])\s+(?=[A-Z0-9\"'])|(?<=[.!?])$", line) if s.strip())
    return parts


def _has(text, words):
    t = f" {text.lower()} "
    return any((f" {w}" in t) if w.endswith(" ") or " " in w or not w.isalpha() else re.search(rf"\b{re.escape(w)}\b", t) for w in words)


def find_owner(sentence):
    s = sentence.strip()
    m = re.search(r"@(\w+)", s)
    if m:
        return m.group(1).title()
    m = re.search(r"\b(?i:ask|tell|remind|have|get)\s+([A-Z][a-z]+)\s+to\b", s)
    if m and m.group(1) not in NOT_NAMES:
        return m.group(1)
    m = re.search(r"\b([A-Z][a-z]+)\s+(?:will|needs to|need to|has to|should|must|is going to|said (?:she|he|they)'?d|agreed to|promised to|offered to|is handling|owns)\b", s)
    if m and m.group(1) not in NOT_NAMES:
        return m.group(1)
    m = re.search(r"\b(?:owner|assigned to|assignee)\s*[:=]?\s*([A-Z][a-z]+)", s)
    if m:
        return m.group(1)
    return DEFAULT_OWNER


def find_location(sentence):
    m = re.search(r"\b(?:at|@)\s+(?:the\s+)?([A-Z][\w'&.-]*(?:\s+(?:[A-Z][\w'&.-]*|of|and|&))*)", sentence)
    if m:
        loc = m.group(1).strip(" .,")
        if loc.split()[0] not in NOT_NAMES and not re.match(r"^\d", loc):
            return loc
    return ""


def find_priority(sentence, due, today):
    if _has(sentence, HIGH_WORDS) or (due and due <= today + timedelta(days=1)):
        return "High"
    if _has(sentence, LOW_WORDS):
        return "Low"
    return "Medium"


def _clean_title(sentence, remove=()):
    s = sentence
    for phrase in remove:
        if phrase:
            s = re.sub(rf"(?:\b(?:at|on|by|from|around)\s+)?{re.escape(phrase)}", " ", s, flags=re.I)
    s = re.sub(r"\b(?:on|by|at|before|until|for|this|next|from)\s*(?=[,.;!?]|$)", "", s.strip(), flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" ,.;:!?-")
    s = re.sub(r"\s+(?:on|by|at|before|until|for|this|next|from|and|the)$", "", s, flags=re.I).strip(" ,.;:!?-")
    s = s[:1].upper() + s[1:]
    return s[:90].rstrip() + ("…" if len(s) > 90 else "")


def _task_title(sentence, cue_end, remove):
    body = sentence[cue_end:] if cue_end else sentence
    body = re.sub(r"^\s*(?:also|then|and|really|definitely|please)\s+", "", body, flags=re.I)
    body = re.sub(r"^\s*(?i:ask|tell|remind|have|get)\s+[A-Z][a-z]+\s+to\s+", "", body)
    return _clean_title(body, remove)


def _event_title(sentence, remove):
    s = re.sub(r"^\s*(?:also|and|then|so|oh|ok|okay)[, ]+", "", sentence, flags=re.I)
    s = re.sub(r"^\s*(?:i|we)\s*(?:'ve|have|has)?\s*(?:got|have|'ve got|has)?\s*(?:an?|the|my|our)?\s+(?=\w)", "", s, flags=re.I)
    s = re.sub(r"^\s*(?:there\s*(?:is|'s)|there\s+will\s+be|remember|don'?t forget)\s+(?:an?|the|my|our)?\s*", "", s, flags=re.I)
    s = re.sub(r"^\s*(?:is|are)\s+", "", s, flags=re.I)
    return re.sub(r"\s+(?:is|are|will be)(?=\s+at\b|$)", "", _clean_title(s, remove))


def _task_cue(sentence):
    """Return the index where the action starts, or None when the sentence is not a task."""
    for cue in TASK_CUES:
        m = re.search(rf"(?:^|\b){cue}\s+", sentence, flags=re.I)
        if m:
            return m.end()
    m = re.search(r"\b(?i:ask|tell|remind|have)\s+[A-Z][a-z]+\s+to\s+", sentence)
    if m:
        return m.start()
    m = re.search(r"\b[A-Z][a-z]+\s+(?:will|needs to|has to|should|must|agreed to|promised to|offered to)\s+", sentence)
    if m and m.group(0).split()[0] not in NOT_NAMES:
        return m.end()
    first = sentence.strip().lower()
    for verb in sorted(IMPERATIVE_VERBS, key=len, reverse=True):
        if first.startswith(verb + " "):
            return 0
    return None


# ---------- mood, tags, summary ----------

def score_mood(text):
    words = re.findall(r"[a-z']+", text.lower())
    score = 0
    for i, w in enumerate(words):
        sign = 1 if w in POSITIVE else -1 if w in NEGATIVE else 0
        if sign and any(prev in NEGATORS for prev in words[max(0, i - 2):i]):
            sign = -sign
        score += sign
    score = max(-5, min(5, score))
    return score, mood_label(score)


def mood_label(score):
    if score >= 3:
        return MOODS[0]
    if score >= 1:
        return MOODS[1]
    if score == 0:
        return MOODS[2]
    if score >= -2:
        return MOODS[3]
    return MOODS[4]


def find_tags(text, limit=5):
    """Topics ranked by how many of their keywords appear."""
    t = text.lower()
    counts = {tag: sum(1 for w in words if re.search(rf"\b{re.escape(w)}\b", t)) for tag, words in TAGS.items()}
    ranked = sorted((tag for tag, n in counts.items() if n), key=lambda tag: -counts[tag])
    return ranked[:limit]


def _reflection(tasks, events, mood_score):
    notes = []
    if len(tasks) >= 5:
        notes.append(f"You listed {len(tasks)} to-dos. Pick the top 3 for today and park the rest.")
    owners = {t["owner"] for t in tasks if t["owner"] != DEFAULT_OWNER}
    if owners:
        notes.append(f"Some items belong to {', '.join(sorted(owners))}; a quick message today keeps them moving.")
    if events:
        notes.append(f"{len(events)} calendar item(s) found. Download the .ics file to add them to your phone calendar.")
    if mood_score <= -2:
        notes.append("This sounded like a heavy day. Something small and kind for yourself tonight counts as a task too.")
    elif mood_score >= 3:
        notes.append("Good energy today. Note what made it work so you can repeat it.")
    return " ".join(notes) or "Captured. Come back tomorrow and keep the streak going."


# ---------- engines ----------

def analyze_rules(text, today=None):
    today = today or date.today()
    tasks, events, ideas = [], [], []
    for sentence in split_sentences(text):
        if any(re.search(c, sentence, flags=re.I) for c in IDEA_CUES) and not _task_cue(sentence):
            ideas.append(sentence.strip())
            continue
        when, date_phrase = find_date(sentence, today)
        start, end, time_phrase = find_times(sentence)
        cue = _task_cue(sentence)
        is_event = _has(sentence, EVENT_WORDS) or (time_phrase and when is not None)
        is_deadline = _has(sentence, DEADLINE_WORDS) or bool(re.search(r"\bby\s+" + re.escape(date_phrase.split()[-1].lower()) if date_phrase else r"$^", sentence.lower()))
        is_reminder = _has(sentence, REMINDER_WORDS)
        past = re.search(r"\b(?:had|went|was|were|met|did|attended|visited|saw|enjoyed|finished|got back)\b", sentence, flags=re.I)
        if past and cue is None and (when is None or when <= today):
            continue  # a diary note about something that already happened
        booking = re.search(r"\b(?:book|schedule|make|set up|arrange)\b", sentence, flags=re.I)

        if is_event and (when or time_phrase) and not (cue is not None and booking) and not is_deadline:
            kind = "Appointment" if _has(sentence, APPOINTMENT_WORDS) else "Reminder" if is_reminder else "Event"
            events.append({
                "title": _event_title(sentence, [date_phrase, time_phrase]),
                "kind": kind, "date": str(when or today), "start_time": start, "end_time": end,
                "location": find_location(sentence.replace(time_phrase, "") if time_phrase else sentence), "notes": "",
            })
            continue
        if cue is not None or (is_deadline and when) or is_reminder:
            title = _task_title(sentence, cue or 0, [date_phrase, time_phrase])
            if not title:
                continue
            task = {
                "title": title, "owner": find_owner(sentence), "due_date": str(when) if when else "",
                "priority": find_priority(sentence, when, today), "notes": "",
            }
            tasks.append(task)
            if when and is_deadline:
                events.append({"title": f"Due: {title}", "kind": "Deadline", "date": str(when), "start_time": start, "end_time": "", "location": "", "notes": "From your task list"})
            elif when and (start or is_reminder):
                events.append({"title": title, "kind": "Reminder", "date": str(when), "start_time": start, "end_time": end, "location": "", "notes": ""})

    mood_score, mood = score_mood(text)
    first = split_sentences(text)[:2]
    summary = " ".join(first)
    if len(summary) > 220:
        summary = summary[:217].rstrip() + "…"
    counts = f"{len(tasks)} task(s), {len(events)} calendar item(s), {len(ideas)} idea(s) found."
    return {
        "summary": f"{summary} ({counts})" if summary else counts,
        "mood": mood, "mood_score": mood_score, "tags": find_tags(text), "reflection": _reflection(tasks, events, mood_score),
        "tasks": tasks, "events": events, "ideas": ideas, "engine": "rules",
    }


SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "Two or three sentences in second person."},
        "mood": {"type": "string", "enum": MOODS},
        "mood_score": {"type": "integer", "description": "-5 (very rough) to 5 (great)."},
        "tags": {"type": "array", "items": {"type": "string"}},
        "reflection": {"type": "string", "description": "One or two kind, practical suggestions."},
        "tasks": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "title": {"type": "string"}, "owner": {"type": "string"},
                "due_date": {"type": "string", "description": "YYYY-MM-DD or empty"},
                "priority": {"type": "string", "enum": PRIORITIES}, "notes": {"type": "string"},
            },
            "required": ["title", "owner", "due_date", "priority", "notes"], "additionalProperties": False,
        }},
        "events": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "title": {"type": "string"}, "kind": {"type": "string", "enum": EVENT_KINDS},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "start_time": {"type": "string", "description": "HH:MM 24h or empty"}, "end_time": {"type": "string", "description": "HH:MM 24h or empty"},
                "location": {"type": "string"}, "notes": {"type": "string"},
            },
            "required": ["title", "kind", "date", "start_time", "end_time", "location", "notes"], "additionalProperties": False,
        }},
        "ideas": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "mood", "mood_score", "tags", "reflection", "tasks", "events", "ideas"],
    "additionalProperties": False,
}

SYSTEM = """You turn a person's private journal entry into organized, actionable notes.
Rules:
- Tasks: concrete things someone should do. Start titles with a verb, keep them short. Owner is "Me" for the writer; use a person's first name when the text gives the action to someone else ("ask Raj to...", "Priya will..."). due_date only when the text implies one.
- Events: anything with a date or time that belongs on a calendar (appointments, meetings, classes, trips, birthdays). Use kind "Deadline" for due dates of tasks, "Reminder" for remind-me items. Resolve relative dates ("next Tuesday", "in 2 weeks", "tomorrow") against today's date. Times in 24h HH:MM; leave empty if not stated.
- Do not invent tasks, people, dates or places that are not in the text. Past events already done are not tasks or events.
- Ideas: loose ideas or wishes worth keeping that are not yet tasks.
- Tags: 1-5 short lowercase topics.
- Mood: pick the label that fits the writer's overall tone; mood_score from -5 to 5.
- Summary and reflection: warm, brief, no medical or legal advice."""


def _api_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    try:
        import streamlit as st

        return st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:
        return ""


def ai_available():
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(_api_key())


def _valid_date(s):
    try:
        return str(date.fromisoformat(str(s).strip()))
    except ValueError:
        return ""


def _valid_time(s):
    m = re.match(r"^\s*(\d{1,2}):(\d{2})", str(s or ""))
    return _hm(m.group(1), m.group(2), None) if m else ""


def normalize(result, today):
    """Clean model output so the rest of the app can trust the shape."""
    out = {
        "summary": str(result.get("summary", "")).strip(),
        "mood_score": max(-5, min(5, int(result.get("mood_score", 0) or 0))),
        "tags": [str(t).strip().lower() for t in result.get("tags", []) if str(t).strip()][:6],
        "reflection": str(result.get("reflection", "")).strip(),
        "ideas": [str(i).strip() for i in result.get("ideas", []) if str(i).strip()],
        "tasks": [], "events": [],
    }
    out["mood"] = result.get("mood") if result.get("mood") in MOODS else mood_label(out["mood_score"])
    for t in result.get("tasks", []):
        if str(t.get("title", "")).strip():
            out["tasks"].append({
                "title": str(t["title"]).strip(), "owner": str(t.get("owner") or DEFAULT_OWNER).strip() or DEFAULT_OWNER,
                "due_date": _valid_date(t.get("due_date", "")), "priority": t.get("priority") if t.get("priority") in PRIORITIES else "Medium",
                "notes": str(t.get("notes", "")).strip(),
            })
    for e in result.get("events", []):
        d = _valid_date(e.get("date", ""))
        if str(e.get("title", "")).strip() and d:
            out["events"].append({
                "title": str(e["title"]).strip(), "kind": e.get("kind") if e.get("kind") in EVENT_KINDS else "Event", "date": d,
                "start_time": _valid_time(e.get("start_time")), "end_time": _valid_time(e.get("end_time")),
                "location": str(e.get("location", "")).strip(), "notes": str(e.get("notes", "")).strip(),
            })
    return out


def analyze_ai(text, today=None, client=None):
    """Ask Claude for structured JSON. Raises on any failure so the caller can fall back."""
    import anthropic

    today = today or date.today()
    client = client or anthropic.Anthropic(api_key=_api_key())
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
        system=SYSTEM,
        messages=[{"role": "user", "content": f"Today is {today:%A, %Y-%m-%d}.\n\nJournal entry:\n<entry>\n{text}\n</entry>"}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("The model declined this entry.")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("The answer was cut off.")
    raw = next(b.text for b in response.content if b.type == "text")
    out = normalize(json.loads(raw), today)
    out["engine"] = "ai"
    return out


def analyze(text, today=None, use_ai=True, client=None):
    """Best available analysis; the result's 'engine' says which ran and 'note' explains any fallback."""
    today = today or date.today()
    if use_ai and (client is not None or ai_available()):
        try:
            return analyze_ai(text, today, client)
        except Exception as exc:  # any API, network or parsing problem falls back to the offline parser
            result = analyze_rules(text, today)
            result["note"] = f"AI analysis was unavailable ({type(exc).__name__}: {str(exc)[:120]}), so the offline parser was used."
            return result
    return analyze_rules(text, today)
