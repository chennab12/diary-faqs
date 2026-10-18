"""Diary FAQs: write a free-form journal entry and turn it into tasks, calendar events and ideas."""
import calendar
from datetime import date, datetime, timedelta
from html import escape
from urllib.parse import urlencode

import pandas as pd
import streamlit as st

from analyzer import MODEL, MOODS, ai_available, analyze
from content import COMMON_MISTAKES, DATE_WORDS, FAQS, PIPELINE, SAMPLE_ENTRIES, WRITING_TIPS
from ics_export import build_ics
from storage import DEFAULT_OWNER, EVENT_KINDS, PRIORITIES, STATUSES, Store, default_path
from visuals import show

st.set_page_config(page_title="Diary FAQs", page_icon="📔", layout="wide")

HOME = "🏠 Today"
WRITE = "✍️ Write"
TASKS = "✅ Tasks"
CALENDAR = "📅 Calendar"
JOURNAL = "📔 Journal"
IDEAS = "💡 Ideas"
INSIGHTS = "📊 Insights"
FAQ = "❓ FAQs & tips"
SETTINGS = "⚙️ Settings & backup"
PAGES = [HOME, WRITE, TASKS, CALENDAR, JOURNAL, IDEAS, INSIGHTS, FAQ, SETTINGS]
KIND_ICON = {"Event": "📅", "Appointment": "🩺", "Deadline": "⏰", "Reminder": "🔔"}
PRIORITY_ICON = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}

store = Store()
today = date.today()


def go(page):
    st.session_state["section"] = page


def to_date(value):
    """Data editor cells come back as date, Timestamp, string or NaT; normalize to 'YYYY-MM-DD' or ''."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    if isinstance(value, str):
        return value[:10]
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat() if isinstance(value, date) else str(value)[:10]


def as_date(text):
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None


def fmt_time(hhmm):
    if not hhmm:
        return ""
    h, m = (int(x) for x in hhmm.split(":"))
    return f"{(h % 12) or 12}:{m:02d} {'am' if h < 12 else 'pm'}"


def google_link(e):
    d = as_date(e["date"])
    if e.get("start_time"):
        start = datetime.combine(d, datetime.strptime(e["start_time"], "%H:%M").time())
        end = datetime.combine(d, datetime.strptime(e["end_time"], "%H:%M").time()) if e.get("end_time") else start + timedelta(hours=1)
        dates = f"{start:%Y%m%dT%H%M%S}/{max(end, start + timedelta(minutes=15)):%Y%m%dT%H%M%S}"
    else:
        dates = f"{d:%Y%m%d}/{d + timedelta(days=1):%Y%m%d}"
    params = {"action": "TEMPLATE", "text": e["title"], "dates": dates, "details": e.get("notes") or e.get("kind", ""), "location": e.get("location", "")}
    return "https://calendar.google.com/calendar/render?" + urlencode(params)


def mistakes_table():
    st.subheader("⚠️ Common mistakes")
    st.table(pd.DataFrame(COMMON_MISTAKES, columns=["Mistake", "Do this instead"]))


def due_label(t):
    d = as_date(t["due_date"])
    if not d:
        return ""
    if t["done"]:
        return d.strftime("%b %d")
    if d < today:
        return f"⚠️ overdue ({d:%b %d})"
    if d == today:
        return "today"
    if d == today + timedelta(days=1):
        return "tomorrow"
    return d.strftime("%a %b %d")


def toggle_task(task_id):
    store.update_task(task_id, done=1 if st.session_state[f"chk_{task_id}"] else 0)


def task_checklist(tasks, prefix=""):
    for t in tasks:
        label = f"{PRIORITY_ICON.get(t['priority'], '')} {t['title']}"
        extra = " · ".join(x for x in [t["owner"] if t["owner"] != DEFAULT_OWNER else "", due_label(t), t["status"] if t["status"] not in ("To do", "Done") else ""] if x)
        st.checkbox(f"{label}" + (f"  ·  _{extra}_" if extra else ""), value=bool(t["done"]), key=f"chk_{t['id']}", on_change=toggle_task, args=(t["id"],))


# ---------------- sidebar ----------------
st.sidebar.title("📔 Diary FAQs")
st.sidebar.caption("Write freely. Let AI turn it into tasks and calendar items.")
if "section" not in st.session_state:
    st.session_state["section"] = HOME
st.sidebar.radio("Go to", PAGES, key="section")
st.sidebar.divider()
st.sidebar.markdown(f"**AI analysis:** {'🟢 on (Claude)' if ai_available() else '⚪ offline parser'}")
st.sidebar.caption("Your diary stays in a local file. With AI on, only the entry you analyze is sent to the Claude API.")
section = st.session_state["section"]


# ---------------- pages ----------------
def page_home():
    st.title("🏠 Today")
    st.caption(today.strftime("%A, %B %d, %Y"))
    show("How it works", PIPELINE)
    tasks = store.tasks()
    open_tasks = [t for t in tasks if not t["done"]]
    overdue = [t for t in open_tasks if t["due_date"] and t["due_date"] < str(today)]
    due_soon = [t for t in open_tasks if t["due_date"] and str(today) <= t["due_date"] <= str(today + timedelta(days=2))]
    events_today = store.events(today, today)
    week_events = store.events(today, today + timedelta(days=7))
    c = st.columns(5)
    c[0].metric("📅 Today", len(events_today))
    c[1].metric("🗓️ Next 7 days", len(week_events))
    c[2].metric("✅ Open tasks", len(open_tasks))
    c[3].metric("⚠️ Overdue", len(overdue))
    c[4].metric("🔥 Journal streak", f"{store.journal_streak(today)} days")
    st.button("✍️ Write today's entry", type="primary", on_click=go, args=(WRITE,))

    left, right = st.columns(2)
    with left:
        st.subheader("📅 Today's agenda")
        if not events_today:
            st.info("Nothing on the calendar today.")
        for e in events_today:
            when = fmt_time(e["start_time"]) or "All day"
            st.markdown(f"{KIND_ICON.get(e['kind'], '📅')} **{when}** · {escape(e['title'])}" + (f" · 📍 {escape(e['location'])}" if e["location"] else ""))
        st.subheader("🗓️ Coming up")
        later = [e for e in week_events if e["date"] > str(today)]
        if not later:
            st.caption("Nothing else this week.")
        for e in later:
            st.markdown(f"{KIND_ICON.get(e['kind'], '📅')} {as_date(e['date']):%a %b %d} {fmt_time(e['start_time'])} · {escape(e['title'])}")
    with right:
        st.subheader("🎯 Focus: overdue and due soon")
        focus = overdue + [t for t in due_soon if t not in overdue]
        if not focus:
            st.success("Nothing overdue or due in the next two days.")
        task_checklist(focus)
        st.subheader("🔴 High priority")
        high = [t for t in open_tasks if t["priority"] == "High" and t not in focus]
        if not high:
            st.caption("No other high-priority tasks.")
        task_checklist(high[:8])
    entries = store.entries()
    if entries:
        st.subheader("📔 Latest entry")
        e = entries[0]
        st.markdown(f"**{as_date(e['entry_date']):%a %b %d}** · {e['mood'] or ''}  \n{e['summary'] or e['body'][:200]}")
    mistakes_table()


def clear_review():
    for key in ("analysis", "review_tasks", "review_events", "review_ideas"):
        st.session_state.pop(key, None)


def _sample_clicked(name):
    st.session_state["draft"] = SAMPLE_ENTRIES[name]
    clear_review()


def _editor_frame(rows, columns, date_cols=()):
    df = pd.DataFrame(rows, columns=columns) if rows else pd.DataFrame(columns=columns)
    for col in date_cols:
        df[col] = pd.to_datetime(df[col].replace("", None), errors="coerce").dt.date
    df.insert(0, "Keep", True)
    return df


def page_write():
    st.title("✍️ Write")
    st.caption("Write the way you think: plans, worries, to-dos, appointments, ideas. Then analyze to turn it into actions.")
    entry_date = st.date_input("Entry date", value=today, key="entry_date")
    cols = st.columns(len(SAMPLE_ENTRIES) + 1)
    cols[0].caption("Try a sample:")
    for i, name in enumerate(SAMPLE_ENTRIES):
        cols[i + 1].button(name, key=f"sample_{i}", on_click=_sample_clicked, args=(name,))
    text = st.text_area("Your entry", key="draft", height=260, placeholder="Dentist on Tuesday at 3:30pm. Need to renew the car registration by Oct 31. Ask Raj to send the deck by Friday…")
    can_ai = ai_available()
    use_ai = st.toggle("Use AI analysis (Claude)", value=can_ai, disabled=not can_ai, key="use_ai",
                       help="Needs ANTHROPIC_API_KEY. Without it the offline parser runs.")
    if not can_ai:
        st.caption("No API key found, so the offline parser will be used. See ⚙️ Settings to turn on AI.")
    b1, b2 = st.columns(2)
    if b1.button("🔍 Analyze", type="primary", disabled=not text.strip()):
        clear_review()
        with st.spinner("Reading your entry…"):
            st.session_state["analysis"] = analyze(text, entry_date, use_ai=use_ai)
            st.session_state["analysis_text"] = text
    if b2.button("💾 Save entry only", disabled=not text.strip()):
        store.add_entry(text, entry_date, {**analyze(text, entry_date, use_ai=False), "tasks": [], "events": [], "ideas": []})
        st.session_state.pop("analysis", None)
        st.success("Entry saved to your journal (no actions added).")

    a = st.session_state.get("analysis")
    if not a:
        mistakes_table()
        return
    if st.session_state.get("analysis_text") != text:
        st.warning("You changed the text after analyzing. Analyze again to refresh the suggestions.")
    st.divider()
    st.subheader("🧠 What I found")
    if a.get("note"):
        st.info(a["note"])
    st.caption(f"Engine: {'Claude (' + MODEL + ')' if a['engine'] == 'ai' else 'offline parser'}")
    c = st.columns([3, 1])
    c[0].markdown(f"**Summary:** {a['summary']}")
    c[1].metric("Mood", a["mood"], a["mood_score"])
    if a["tags"]:
        st.markdown(" ".join(f"`#{t}`" for t in a["tags"]))
    if a["reflection"]:
        st.markdown(f"💬 {a['reflection']}")

    st.markdown("#### ✅ Tasks")
    tasks_df = st.data_editor(
        _editor_frame(a["tasks"], ["title", "owner", "due_date", "priority", "notes"], ["due_date"]),
        key="review_tasks", num_rows="dynamic", width="stretch",
        column_config={
            "Keep": st.column_config.CheckboxColumn("Keep", width="small"),
            "title": st.column_config.TextColumn("Task", required=True),
            "owner": st.column_config.TextColumn("Owner", default=DEFAULT_OWNER),
            "due_date": st.column_config.DateColumn("Due", format="ddd MMM D"),
            "priority": st.column_config.SelectboxColumn("Priority", options=PRIORITIES, default="Medium"),
            "notes": st.column_config.TextColumn("Notes"),
        },
    )
    st.markdown("#### 📅 Calendar items")
    events_df = st.data_editor(
        _editor_frame(a["events"], ["title", "kind", "date", "start_time", "end_time", "location", "notes"], ["date"]),
        key="review_events", num_rows="dynamic", width="stretch",
        column_config={
            "Keep": st.column_config.CheckboxColumn("Keep", width="small"),
            "title": st.column_config.TextColumn("Title", required=True),
            "kind": st.column_config.SelectboxColumn("Type", options=EVENT_KINDS, default="Event"),
            "date": st.column_config.DateColumn("Date", format="ddd MMM D", required=True),
            "start_time": st.column_config.TextColumn("Start (HH:MM)"),
            "end_time": st.column_config.TextColumn("End (HH:MM)"),
            "location": st.column_config.TextColumn("Location"),
            "notes": st.column_config.TextColumn("Notes"),
        },
    )
    st.markdown("#### 💡 Ideas")
    ideas_df = st.data_editor(_editor_frame([[i] for i in a["ideas"]], ["idea"]), key="review_ideas", num_rows="dynamic", width="stretch")

    if st.button("💾 Save entry and add the kept actions", type="primary"):
        keep = lambda df: [r for r in df.to_dict("records") if r.get("Keep") is not False]  # noqa: E731
        tasks = [{**r, "due_date": to_date(r.get("due_date")), "owner": r.get("owner") or DEFAULT_OWNER, "priority": r.get("priority") or "Medium", "notes": r.get("notes") or ""}
                 for r in keep(tasks_df) if str(r.get("title") or "").strip()]
        events = [{**r, "date": to_date(r.get("date")), "kind": r.get("kind") or "Event", "start_time": r.get("start_time") or "", "end_time": r.get("end_time") or "", "location": r.get("location") or "", "notes": r.get("notes") or ""}
                  for r in keep(events_df) if str(r.get("title") or "").strip() and to_date(r.get("date"))]
        ideas = [str(r["idea"]).strip() for r in keep(ideas_df) if str(r.get("idea") or "").strip()]
        store.save_analysis(st.session_state.get("analysis_text", text), entry_date, a, tasks, events, ideas)
        clear_review()
        st.success(f"Saved: {len(tasks)} task(s), {len(events)} calendar item(s), {len(ideas)} idea(s). See ✅ Tasks and 📅 Calendar.")
    mistakes_table()


def page_tasks():
    st.title("✅ Tasks")
    tasks = store.tasks()
    open_tasks = [t for t in tasks if not t["done"]]
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    c = st.columns(4)
    c[0].metric("Open", len(open_tasks))
    c[1].metric("Due today", sum(1 for t in open_tasks if t["due_date"] == str(today)))
    c[2].metric("Overdue", sum(1 for t in open_tasks if t["due_date"] and t["due_date"] < str(today)))
    c[3].metric("Done in last 7 days", sum(1 for t in tasks if t["done"] and t["completed_at"] >= week_ago))

    with st.expander("➕ Add a task"):
        with st.form("add_task", clear_on_submit=True):
            title = st.text_input("Task")
            f = st.columns(4)
            owner = f[0].text_input("Owner", value=DEFAULT_OWNER)
            has_due = f[1].checkbox("Has a due date", value=False)
            due = f[1].date_input("Due", value=today, label_visibility="collapsed")
            priority = f[2].selectbox("Priority", PRIORITIES, index=1)
            status = f[3].selectbox("Status", STATUSES)
            notes = st.text_input("Notes")
            if st.form_submit_button("Add task") and title.strip():
                store.add_task(title, owner, due if has_due else "", priority, notes, status=status)
                st.rerun()

    owners = sorted({t["owner"] for t in tasks})
    f = st.columns([2, 2, 2, 1])
    view = f[0].radio("Show", ["Open", "All", "Done"], horizontal=True, key="task_view")
    owner = f[1].selectbox("Owner", ["Everyone"] + owners, key="task_owner")
    search = f[2].text_input("Search", key="task_search")
    board = f[3].toggle("Board", key="task_board")
    shown = [t for t in tasks if (view == "All" or (view == "Done") == bool(t["done"]))
             and (owner == "Everyone" or t["owner"] == owner) and (not search or search.lower() in (t["title"] + t["notes"]).lower())]

    if board:
        cols = st.columns(len(STATUSES))
        for col, status in zip(cols, STATUSES):
            items = [t for t in shown if t["status"] == status] if view != "Open" or status != "Done" else []
            col.markdown(f"**{status}** ({len(items)})")
            for t in items:
                col.markdown(f"{PRIORITY_ICON[t['priority']]} {escape(t['title'])}  \n<small>{escape(t['owner'])} {('· ' + due_label(t)) if t['due_date'] else ''}</small>", unsafe_allow_html=True)
    else:
        df = pd.DataFrame(shown, columns=["id", "done", "title", "owner", "status", "due_date", "priority", "notes"])
        df["done"] = df["done"].astype(bool)
        df["due_date"] = pd.to_datetime(df["due_date"].replace("", None), errors="coerce").dt.date
        df["delete"] = False
        edited = st.data_editor(
            df, key=f"task_table_{view}_{owner}_{search}", hide_index=True, width="stretch", disabled=["id"],
            column_order=["done", "title", "owner", "status", "due_date", "priority", "notes", "delete"],
            column_config={
                "done": st.column_config.CheckboxColumn("✔", width="small"),
                "title": st.column_config.TextColumn("Task", required=True),
                "owner": st.column_config.TextColumn("Owner"),
                "status": st.column_config.SelectboxColumn("Status", options=STATUSES, required=True),
                "due_date": st.column_config.DateColumn("Due", format="ddd MMM D"),
                "priority": st.column_config.SelectboxColumn("Priority", options=PRIORITIES, required=True),
                "notes": st.column_config.TextColumn("Notes"),
                "delete": st.column_config.CheckboxColumn("🗑️", width="small"),
            },
        )
        if st.button("💾 Save task changes", type="primary"):
            changed = save_task_edits(df, edited)
            st.success(f"Saved {changed} change(s).")
            st.rerun()
        st.download_button("⬇️ Download tasks (CSV)", pd.DataFrame(tasks).to_csv(index=False) if tasks else "", "tasks.csv", "text/csv", disabled=not tasks)
    mistakes_table()


def save_task_edits(before, after):
    changed = 0
    old = {r["id"]: r for r in before.to_dict("records")}
    for r in after.to_dict("records"):
        o = old.get(r["id"])
        if o is None:
            continue
        if r.get("delete"):
            store.delete_task(r["id"])
            changed += 1
            continue
        fields = {}
        for key in ("title", "owner", "status", "priority", "notes"):
            if (r.get(key) or "") != (o.get(key) or ""):
                fields[key] = r.get(key) or ""
        if bool(r["done"]) != bool(o["done"]):
            fields["done"] = 1 if r["done"] else 0
        if to_date(r.get("due_date")) != to_date(o.get("due_date")):
            fields["due_date"] = to_date(r.get("due_date"))
        if fields:
            store.update_task(r["id"], **fields)
            changed += 1
    return changed


def month_grid(year, month, events, tasks):
    by_day = {}
    for e in events:
        by_day.setdefault(e["date"], []).append(f"{KIND_ICON.get(e['kind'], '📅')} {fmt_time(e['start_time'])} {e['title']}".replace("  ", " "))
    deadlines = {(e["date"], e["title"]) for e in events}
    for t in tasks:
        if t["due_date"] and not t["done"] and (t["due_date"], f"Due: {t['title']}") not in deadlines:
            by_day.setdefault(t["due_date"], []).append(f"✅ {t['title']}")
    style = """
    .dcal{width:100%;border-collapse:collapse;table-layout:fixed;font-family:system-ui,Arial,sans-serif}
    .dcal th{padding:6px;font-size:13px;color:#555}
    .dcal td{border:1px solid #ddd;vertical-align:top;height:92px;padding:4px;font-size:12px;overflow:hidden}
    .dcal .dnum{font-weight:700;font-size:13px}.dcal .dtoday{background:#fff6d6}.dcal .dout{background:#f6f6f6;color:#aaa}
    .dcal .ditem{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    @media(prefers-color-scheme:dark){.dcal td{border-color:#444}.dcal th{color:#bbb}.dcal .dtoday{background:#4a3f12}.dcal .dout{background:#222;color:#666}}
    @media(max-width:640px){.dcal td{height:60px;font-size:10px}}
    """
    rows = []
    for week in calendar.Calendar(firstweekday=6).monthdatescalendar(year, month):
        cells = []
        for d in week:
            cls = "dtoday" if d == today else "dout" if d.month != month else ""
            items = by_day.get(str(d), [])
            body = "".join(f'<div class="ditem" title="{escape(i)}">{escape(i)}</div>' for i in items[:4])
            if len(items) > 4:
                body += f"<div>+{len(items) - 4} more</div>"
            cells.append(f'<td class="{cls}"><div class="dnum">{d.day}</div>{body}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    head = "".join(f"<th>{d}</th>" for d in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"])
    st.html(f"<style>{style}</style><table class='dcal'><tr>{head}</tr>{''.join(rows)}</table>")


def page_calendar():
    st.title("📅 Calendar")
    pick = st.date_input("Show month", value=today, key="cal_month")
    year, month = pick.year, pick.month
    first, last = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    tasks = store.tasks()
    st.subheader(f"{calendar.month_name[month]} {year}")
    month_grid(year, month, store.events(first - timedelta(days=7), last + timedelta(days=7)), tasks)
    st.caption("📅 event · 🩺 appointment · ⏰ deadline · 🔔 reminder · ✅ open task due")

    with st.expander("➕ Add a calendar item"):
        with st.form("add_event", clear_on_submit=True):
            title = st.text_input("Title")
            f = st.columns(4)
            kind = f[0].selectbox("Type", EVENT_KINDS)
            day = f[1].date_input("Date", value=today)
            start = f[2].text_input("Start (HH:MM, optional)")
            end = f[3].text_input("End (HH:MM, optional)")
            location = st.text_input("Location")
            if st.form_submit_button("Add") and title.strip():
                store.add_event(title, day, kind, start.strip(), end.strip(), location)
                st.rerun()

    st.subheader("🗓️ Upcoming (next 60 days)")
    upcoming = store.events(today, today + timedelta(days=60))
    if not upcoming:
        st.info("No upcoming calendar items. Write an entry with a date or add one above.")
    else:
        df = pd.DataFrame(upcoming)[["id", "date", "start_time", "end_time", "kind", "title", "location", "notes"]]
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df["google"] = [google_link(e) for e in upcoming]
        df["delete"] = False
        edited = st.data_editor(
            df, key="event_table", hide_index=True, width="stretch", disabled=["id", "google"],
            column_order=["date", "start_time", "end_time", "kind", "title", "location", "notes", "google", "delete"],
            column_config={
                "date": st.column_config.DateColumn("Date", format="ddd MMM D", required=True),
                "start_time": st.column_config.TextColumn("Start"),
                "end_time": st.column_config.TextColumn("End"),
                "kind": st.column_config.SelectboxColumn("Type", options=EVENT_KINDS, required=True),
                "title": st.column_config.TextColumn("Title", required=True),
                "google": st.column_config.LinkColumn("Google", display_text="Add to Google"),
                "delete": st.column_config.CheckboxColumn("🗑️", width="small"),
            },
        )
        if st.button("💾 Save calendar changes"):
            old = {r["id"]: r for r in df.to_dict("records")}
            for r in edited.to_dict("records"):
                if r.get("delete"):
                    store.delete_event(r["id"])
                elif r != old.get(r["id"]):
                    store.update_event(r["id"], title=r["title"], kind=r["kind"], date=to_date(r["date"]), start_time=r["start_time"],
                                       end_time=r["end_time"], location=r["location"], notes=r["notes"])
            st.rerun()

    st.subheader("⬇️ Add to your calendar app")
    include_tasks = st.checkbox("Include open tasks as to-dos", value=False, key="ics_tasks")
    all_future = store.events(today - timedelta(days=30))
    ics = build_ics(all_future, [t for t in tasks if not t["done"]] if include_tasks else [])
    st.download_button("⬇️ Download .ics", ics, "diary-actions.ics", "text/calendar", type="primary", disabled=not (all_future or include_tasks))
    st.caption("Import the file in Google Calendar (Settings → Import), Apple Calendar (File → Import) or Outlook (Add calendar → Upload).")
    mistakes_table()


def page_journal():
    st.title("📔 Journal")
    search = st.text_input("🔎 Search entries, summaries and tags", key="journal_search")
    entries = store.entries(search)
    if not entries:
        st.info("No entries yet. Start on the ✍️ Write page." if not search else "No entries match.")
    tasks, events = store.tasks(), store.events()
    md = []
    for e in entries:
        d = as_date(e["entry_date"])
        with st.expander(f"{d:%a %b %d, %Y} · {e['mood'] or ''} · {(e['summary'] or e['body'])[:90]}"):
            st.markdown(e["body"].replace("\n", "  \n"))
            if e["tags"]:
                st.markdown(" ".join(f"`#{t}`" for t in e["tags"]))
            if e["reflection"]:
                st.caption(f"💬 {e['reflection']}")
            linked_t = [t for t in tasks if t["entry_id"] == e["id"]]
            linked_e = [x for x in events if x["entry_id"] == e["id"]]
            if linked_t or linked_e:
                st.markdown("**Actions from this entry:** " + ", ".join([("✔ " if t["done"] else "☐ ") + t["title"] for t in linked_t] + [f"{KIND_ICON.get(x['kind'], '📅')} {x['title']} ({x['date']})" for x in linked_e]))
            c = st.columns([2, 1])
            also = c[0].checkbox("Also delete its tasks, events and ideas", key=f"del_all_{e['id']}")
            if c[1].button("🗑️ Delete entry", key=f"del_{e['id']}"):
                store.delete_entry(e["id"], with_actions=also)
                st.rerun()
        md.append(f"## {d:%A, %B %d, %Y}\n\n{e['mood']}\n\n{e['body']}\n")
    if entries:
        st.download_button("⬇️ Download journal (Markdown)", "\n".join(md), "journal.md", "text/markdown")
    mistakes_table()


def page_ideas():
    st.title("💡 Ideas")
    st.caption("Loose ideas from your entries. Turn one into a task when you're ready.")
    with st.form("add_idea", clear_on_submit=True):
        text = st.text_input("New idea")
        if st.form_submit_button("Add idea") and text.strip():
            store.add_idea(text)
            st.rerun()
    ideas = store.ideas()
    if not ideas:
        st.info("No ideas yet. Sentences like 'What if…' or 'Idea:' are collected here.")
    for i in ideas:
        c = st.columns([6, 1, 1])
        c[0].markdown(f"💡 {escape(i['text'])}")
        if c[1].button("➡️ Task", key=f"idea_task_{i['id']}"):
            store.add_task(i["text"][:90], DEFAULT_OWNER, "", "Low", "From an idea", i["entry_id"])
            store.delete_idea(i["id"])
            st.rerun()
        if c[2].button("🗑️", key=f"idea_del_{i['id']}"):
            store.delete_idea(i["id"])
            st.rerun()
    mistakes_table()


def page_insights():
    st.title("📊 Insights")
    entries, tasks = store.entries(), store.tasks()
    if not entries and not tasks:
        st.info("Write a few entries and insights will appear here.")
        mistakes_table()
        return
    done = sum(1 for t in tasks if t["done"])
    c = st.columns(4)
    c[0].metric("Entries", len(entries))
    c[1].metric("Streak", f"{store.journal_streak(today)} days")
    c[2].metric("Tasks done", f"{done}/{len(tasks)}")
    c[3].metric("Completion", f"{(done / len(tasks) * 100) if tasks else 0:.0f}%")
    if entries:
        st.subheader("🙂 Mood over time")
        mood = pd.DataFrame(entries).groupby("entry_date")["mood_score"].mean().rename("Mood score (-5 to 5)")
        mood.index = pd.to_datetime(mood.index)
        st.line_chart(mood)
        st.caption(" · ".join(MOODS) + ". A rough writing signal, not a diagnosis.")
        st.subheader("🏷️ What you write about")
        tags = pd.Series([t for e in entries for t in e["tags"]], dtype="object").value_counts().rename("Entries")
        if len(tags):
            st.bar_chart(tags)
    if tasks:
        st.subheader("👥 Tasks by owner and status")
        table = pd.crosstab(pd.Series([t["owner"] for t in tasks], name="Owner"), pd.Series([t["status"] for t in tasks], name="Status"))
        st.dataframe(table.reindex(columns=[s for s in STATUSES if s in table.columns]), width="stretch")
    mistakes_table()


def page_faq():
    st.title("❓ FAQs & tips")
    show("From diary to done", PIPELINE)
    st.subheader("✍️ Write it like this")
    st.table(pd.DataFrame(WRITING_TIPS, columns=["You write", "You get"]))
    st.subheader("🗓️ Date and time words the offline parser understands")
    st.table(pd.DataFrame(DATE_WORDS, columns=["Words", "Meaning"]))
    st.caption("With AI analysis on, Claude reads looser phrasing too. Either way, you review everything before it is saved.")
    st.subheader("Questions")
    for q, a in FAQS:
        with st.expander(q):
            st.markdown(a)
    mistakes_table()


def page_settings():
    st.title("⚙️ Settings & backup")
    st.subheader("🤖 AI analysis")
    if ai_available():
        st.success(f"An Anthropic API key was found. Entries are analyzed with {MODEL}, with the offline parser as a fallback.")
    else:
        st.warning("No Anthropic API key found, so the offline parser is used.")
    st.markdown(
        "To turn on AI, set `ANTHROPIC_API_KEY` in your environment, or add it to `.streamlit/secrets.toml`:\n\n"
        "```toml\nANTHROPIC_API_KEY = \"sk-ant-...\"\n```\n"
        "Optional: `DIARY_MODEL` picks another Claude model and `DIARY_EFFORT` (low, medium, high) trades speed for depth."
    )
    st.subheader("💾 Your data")
    st.markdown(f"Database file: `{default_path()}`")
    st.download_button("⬇️ Download backup (JSON)", store.export_json(), f"diary-backup-{today}.json", "application/json")
    upload = st.file_uploader("⬆️ Restore from a backup (adds to what is already here)", type=["json"], key="restore")
    if upload is not None and st.button("Restore backup"):
        n = store.import_json(upload.getvalue().decode("utf-8"))
        st.success(f"Restored {n[0]} entries, {n[1]} tasks and {n[2]} calendar items.")
    mistakes_table()


{HOME: page_home, WRITE: page_write, TASKS: page_tasks, CALENDAR: page_calendar, JOURNAL: page_journal, IDEAS: page_ideas,
 INSIGHTS: page_insights, FAQ: page_faq, SETTINGS: page_settings}[section]()
