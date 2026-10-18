"""Smoke tests: every page renders, and the write → analyze → save → check off flow works."""
from datetime import date, timedelta

from streamlit.testing.v1 import AppTest

from storage import Store


def run(section=None):
    at = AppTest.from_file("../app.py", default_timeout=30)
    if section is not None:
        at.session_state["section"] = section
    at.run()
    assert not at.exception, at.exception
    return at


def test_every_page_renders_empty_and_ends_with_mistakes():
    for section in run().sidebar.radio[0].options:
        at = run(section)
        assert any("Common mistakes" in h.value for h in at.subheader), section


def test_every_page_renders_with_data():
    s = Store()
    today = date.today()
    s.add_entry("Felt great", str(today), {"mood": "😀 Great", "mood_score": 3, "tags": ["family"], "summary": "Good day"})
    s.add_task("Overdue thing", due_date=str(today - timedelta(days=2)), priority="High")
    s.add_task("Raj's thing", owner="Raj", status="Waiting")
    s.add_event("Dentist", today, "Appointment", "15:30", "", "Bright Smiles")
    s.add_event("Party", today + timedelta(days=3))
    s.add_idea("Game night")
    for section in run().sidebar.radio[0].options:
        run(section)
    at = run("✅ Tasks")
    at.toggle(key="task_board").set_value(True).run()
    assert not at.exception


def test_write_analyze_save_flow():
    at = run("✍️ Write")
    at.button(key="sample_0").click().run()
    assert "Dentist appointment" in at.text_area(key="draft").value
    next(b for b in at.button if b.label == "🔍 Analyze").click().run()
    assert not at.exception
    assert any("What I found" in h.value for h in at.subheader)
    next(b for b in at.button if b.label.startswith("💾 Save entry and add")).click().run()
    assert not at.exception
    s = Store()
    assert len(s.entries()) == 1
    assert any(t["owner"] == "Raj" for t in s.tasks())
    assert any(e["kind"] == "Appointment" for e in s.events())
    assert s.ideas()


def test_home_checkbox_completes_task():
    s = Store()
    tid = s.add_task("Call mom", due_date=str(date.today()))
    at = run()
    at.checkbox(key=f"chk_{tid}").check().run()
    assert not at.exception
    assert Store().tasks()[0]["status"] == "Done"


def test_add_task_and_event_forms():
    at = run("✅ Tasks")
    at.text_input[0].input("Book flights")
    next(b for b in at.button if b.label == "Add task").click().run()
    assert Store().tasks()[0]["title"] == "Book flights"
    at = run("📅 Calendar")
    at.text_input[0].input("Lunch with Ana")
    next(b for b in at.button if b.label == "Add").click().run()
    assert Store().events()[0]["title"] == "Lunch with Ana"
