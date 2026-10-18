"""The offline parser and the AI path share one output shape."""
import json
from datetime import date
from types import SimpleNamespace

import pytest

from analyzer import analyze, analyze_rules, find_date, find_owner, find_times, normalize, score_mood
from content import SAMPLE_ENTRIES

TODAY = date(2026, 10, 18)  # a Sunday


@pytest.mark.parametrize("text,expected", [
    ("tomorrow", date(2026, 10, 19)),
    ("day after tomorrow", date(2026, 10, 20)),
    ("tonight", TODAY),
    ("on Tuesday", date(2026, 10, 20)),
    ("next Thursday", date(2026, 10, 22)),
    ("this Sunday", TODAY),
    ("Sunday", date(2026, 10, 25)),
    ("in 3 days", date(2026, 10, 21)),
    ("in two weeks", date(2026, 11, 1)),
    ("in a month", date(2026, 11, 18)),
    ("by Oct 31", date(2026, 10, 31)),
    ("November 2nd", date(2026, 11, 2)),
    ("31 December", date(2026, 12, 31)),
    ("11/14", date(2026, 11, 14)),
    ("1/5", date(2027, 1, 5)),
    ("10/15", date(2026, 10, 15)),
    ("2027-02-03", date(2027, 2, 3)),
    ("3/4/27", date(2027, 3, 4)),
    ("end of month", date(2026, 10, 31)),
    ("next week", date(2026, 10, 19)),
    ("this weekend", date(2026, 10, 24)),
])
def test_dates(text, expected):
    assert find_date(f"Something {text}.", TODAY)[0] == expected


def test_no_date_and_invalid_dates():
    assert find_date("Buy milk", TODAY) == (None, "")
    assert find_date("on 2/30", TODAY)[0] is None


@pytest.mark.parametrize("text,start,end", [
    ("at 3:30pm", "15:30", ""), ("at 9 am", "09:00", ""), ("at 15:45", "15:45", ""), ("at noon", "12:00", ""),
    ("4-5pm", "16:00", "17:00"), ("from 2 to 4pm", "14:00", "16:00"), ("11am-1pm", "11:00", "13:00"),
    ("at 7", "19:00", ""), ("at 9", "09:00", ""), ("12am", "00:00", ""), ("nothing", "", ""),
])
def test_times(text, start, end):
    assert find_times(f"Meeting {text}")[:2] == (start, end)


@pytest.mark.parametrize("sentence,owner", [
    ("Ask Raj to send the deck", "Raj"), ("Priya will book the venue", "Priya"), ("@sam review the doc", "Sam"),
    ("I need to call the bank", "Me"), ("Monday will be busy", "Me"), ("remind Lee to pay", "Lee"),
])
def test_owners(sentence, owner):
    assert find_owner(sentence) == owner


def test_sample_entry_becomes_actions():
    r = analyze_rules(SAMPLE_ENTRIES["Busy family week"], TODAY)
    tasks = {t["title"]: t for t in r["tasks"]}
    assert tasks["Renew the car registration"]["due_date"] == "2026-10-31"
    assert tasks["Send the Q4 budget deck"]["owner"] == "Raj"
    assert tasks["Send the Q4 budget deck"]["due_date"] == "2026-10-23"
    assert tasks["Book the venue for the team dinner"]["owner"] == "Priya"
    assert tasks["Call mom"]["due_date"] == "2026-10-19" and tasks["Call mom"]["priority"] == "High"
    assert any(t["title"].startswith("Pay the PG&E bill") and t["priority"] == "High" for t in r["tasks"])
    events = {e["title"]: e for e in r["events"]}
    dentist = events["Dentist appointment at Bright Smiles"]
    assert (dentist["kind"], dentist["date"], dentist["start_time"], dentist["location"]) == ("Appointment", "2026-10-20", "15:30", "Bright Smiles")
    ptc = events["Parent-teacher conference"]
    assert (ptc["date"], ptc["start_time"], ptc["end_time"]) == ("2026-10-22", "16:00", "17:00")
    assert any(e["kind"] == "Deadline" and e["date"] == "2026-10-31" for e in r["events"])
    assert r["ideas"] == ["What if we started a family game night every Sunday?"]
    assert r["engine"] == "rules" and "work" in r["tags"]


def test_every_sample_parses_cleanly():
    for text in SAMPLE_ENTRIES.values():
        r = analyze_rules(text, TODAY)
        assert r["tasks"] or r["events"]
        for t in r["tasks"]:
            assert t["title"] and t["title"][0].isupper() and t["priority"] in ("High", "Medium", "Low")
        for e in r["events"]:
            date.fromisoformat(e["date"])


def test_past_events_stay_in_the_journal():
    r = analyze_rules("Had a great lunch with Ana today. We went to the park yesterday.", TODAY)
    assert r["events"] == [] and r["tasks"] == []


def test_mood():
    assert score_mood("I feel happy, proud and grateful")[0] == 3
    assert score_mood("I was not happy, tired and stressed")[0] < 0
    assert score_mood("Wrote some notes")[1] == "😐 Neutral"


def test_normalize_cleans_model_output():
    out = normalize({
        "summary": " ok ", "mood": "bogus", "mood_score": 9, "tags": ["Work", ""], "reflection": "", "ideas": ["", "x"],
        "tasks": [{"title": "Do it", "owner": "", "due_date": "not a date", "priority": "Urgent", "notes": ""}, {"title": " "}],
        "events": [{"title": "Dentist", "kind": "Party", "date": "2026-10-20", "start_time": "3:30", "end_time": "bad", "location": "", "notes": ""},
                   {"title": "No date", "date": ""}],
    }, TODAY)
    assert out["mood_score"] == 5 and out["mood"] == "😀 Great" and out["tags"] == ["work"] and out["ideas"] == ["x"]
    assert out["tasks"] == [{"title": "Do it", "owner": "Me", "due_date": "", "priority": "Medium", "notes": ""}]
    assert out["events"][0]["kind"] == "Event" and out["events"][0]["start_time"] == "03:30" and out["events"][0]["end_time"] == ""
    assert len(out["events"]) == 1


class FakeClient:
    def __init__(self, payload=None, error=None, stop_reason="end_turn"):
        self.calls = []
        self.payload, self.error, self.stop_reason = payload, error, stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(stop_reason=self.stop_reason, content=[SimpleNamespace(type="text", text=json.dumps(self.payload))])


AI_PAYLOAD = {
    "summary": "Busy week.", "mood": "🙂 Good", "mood_score": 2, "tags": ["family"], "reflection": "Pick three.", "ideas": [],
    "tasks": [{"title": "Renew registration", "owner": "Me", "due_date": "2026-10-31", "priority": "High", "notes": ""}],
    "events": [{"title": "Dentist", "kind": "Appointment", "date": "2026-10-20", "start_time": "15:30", "end_time": "", "location": "", "notes": ""}],
}


def test_ai_path_uses_structured_output():
    client = FakeClient(AI_PAYLOAD)
    r = analyze("Dentist Tuesday 3:30pm", TODAY, client=client)
    assert r["engine"] == "ai" and r["tasks"][0]["title"] == "Renew registration" and r["events"][0]["start_time"] == "15:30"
    call = client.calls[0]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "Sunday, 2026-10-18" in call["messages"][0]["content"]


@pytest.mark.parametrize("client", [FakeClient(error=RuntimeError("network down")), FakeClient(AI_PAYLOAD, stop_reason="refusal")])
def test_ai_failure_falls_back_to_rules(client):
    r = analyze("Need to buy milk tomorrow", TODAY, client=client)
    assert r["engine"] == "rules" and "offline parser" in r["note"] and r["tasks"][0]["title"] == "Buy milk"


def test_no_key_means_rules():
    assert analyze("Buy milk", TODAY)["engine"] == "rules"
