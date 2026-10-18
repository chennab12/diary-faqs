"""Help text, sample entries, writing tips and FAQs."""

SAMPLE_ENTRIES = {
    "Busy family week": """Long day at work, but I'm proud we shipped the launch. Feeling tired though.
Dentist appointment on Tuesday at 3:30pm at Bright Smiles.
I need to renew the car registration by Oct 31.
Ask Raj to send the Q4 budget deck by Friday.
Priya will book the venue for the team dinner.
Parent-teacher conference next Thursday 4-5pm.
Remember to call mom tomorrow.
Buy milk, eggs and bananas.
Pay the PG&E bill, urgent.
What if we started a family game night every Sunday?""",
    "Work planning": """Good, productive morning. The roadmap review went well and my manager liked the plan.
1:1 with Sam tomorrow at 10am.
I have to finish the launch checklist by Wednesday.
Lee will update the dashboard before the demo.
Demo for the leadership team on Nov 5 at 2pm in Room Everest.
Follow up with the vendor about the contract.
Idea: a weekly 15-minute risk review could catch blockers earlier.""",
    "Rough day": """Honestly a rough day. I felt overwhelmed and behind on everything, and I didn't sleep well.
Need to schedule a doctor checkup.
Don't forget to cancel the gym trial before 11/1.
Maybe I could try a short walk after lunch to reset.
Tonight I'll go to bed by 10.""",
}

PIPELINE = ["Write freely", "AI finds actions", "Review and keep", "Track, check off, export"]

WRITING_TIPS = [
    ("Dentist appointment on Tuesday at 3:30pm", "📅 Appointment on the coming Tuesday, 15:30"),
    ("Parent-teacher conference next Thursday 4-5pm", "📅 Event next week's Thursday, 16:00 to 17:00"),
    ("I need to renew the car registration by Oct 31", "✅ Task due Oct 31 + ⏰ deadline on the calendar"),
    ("Ask Raj to send the budget deck by Friday", "✅ Task owned by Raj, due Friday"),
    ("Priya will book the venue", "✅ Task owned by Priya"),
    ("Remember to call mom tomorrow", "✅ Task due tomorrow, high priority"),
    ("Buy milk and eggs", "✅ Task (starts with an action verb)"),
    ("Pay the bill, urgent", "✅ High-priority task"),
    ("What if we tried a game night on Sundays?", "💡 Idea saved for later"),
    ("Had a great lunch with Ana today", "📔 Stays in your journal only (it already happened)"),
]

DATE_WORDS = [
    ("today / tonight / this morning", "Today"),
    ("tomorrow, day after tomorrow", "+1 day, +2 days"),
    ("Monday, on Monday, this Monday", "The next Monday (today only for 'this' + today's weekday)"),
    ("next Monday", "Monday of next calendar week"),
    ("in 3 days / in two weeks / in a month", "Counted from the entry date"),
    ("next week / this weekend / end of month", "Next Monday / coming Saturday / last day of month"),
    ("Oct 31, 31 October, 10/31, 2026-10-31", "That date; without a year it means the next one"),
    ("3pm, 3:30 pm, 15:30, noon, 4-5pm, at 7", "Start (and end) time; a bare 'at 1'-'7' means pm"),
]

FAQS = [
    ("Where is my diary stored?",
     "In a local SQLite file (diary.db next to app.py, or the path in the DIARY_DB environment variable). Nothing leaves your computer unless you turn on AI analysis."),
    ("What does the AI analysis send, and to whom?",
     "When AI is on, only the text of the entry you are analyzing is sent to Anthropic's Claude API to extract the summary, mood, tasks, events and ideas. Turn the toggle off on the Write page to use the offline parser instead."),
    ("How do I turn on AI analysis?",
     "Set ANTHROPIC_API_KEY as an environment variable, or put ANTHROPIC_API_KEY = \"...\" in .streamlit/secrets.toml (or the Secrets box on Streamlit Community Cloud). The Settings page shows whether a key was found."),
    ("Does it work without an API key?",
     "Yes. The offline parser understands common date words, times, task phrases (need to, remember to, action verbs), owners (ask Raj to, Priya will) and urgency words. It is less flexible than the AI, so always review the suggestions before saving."),
    ("Will it add things to my calendar without asking?",
     "No. Every suggested task, event and idea is shown in an editable table first. Untick Keep for anything you don't want, fix titles or dates, then save."),
    ("How do events get into Google, Apple or Outlook calendar?",
     "The Calendar page has a Download .ics button (import it into any calendar app) and an Add to Google link for each upcoming event. Open tasks can be included as to-dos that Apple Reminders and Outlook understand."),
    ("How do the task checkbox and status work together?",
     "Ticking Done sets status to Done; choosing Done in the status column ticks the box. Unticking moves a task back to To do. Statuses are To do, In progress, Waiting and Done."),
    ("Who is the owner of a task?",
     "Me by default. When you write things like 'ask Raj to…', 'Priya will…' or '@Sam', that person becomes the owner. You can change the owner any time in the task table."),
    ("How are priorities set?",
     "Words like urgent, ASAP or important, or a due date of today or tomorrow, make a task High. Someday, no rush or if I have time make it Low. Everything else is Medium."),
    ("Why did a sentence not become a task or event?",
     "Diary sentences about the past (had, went, met) are kept only as journal text. Add a clear action verb or a date and time, then analyze again, or add the item by hand."),
    ("How do I back up or move my diary?",
     "Settings → Download backup gives a JSON file with every entry, task, event and idea. Restore it on another machine with Upload backup."),
    ("Is this a therapy or medical tool?",
     "No. Mood scores and reflections are simple writing aids, not a diagnosis. If you are in crisis in the US, call or text 988."),
]

COMMON_MISTAKES = [
    ("Writing 'Friday' when you mean a date weeks away", "Use the full date (Nov 21) for anything more than a week out."),
    ("Saving without reviewing", "Glance at the suggestions table; one wrong date can hide an appointment."),
    ("Leaving every task owned by Me", "Name the person ('ask Raj to…') so shared work is visible."),
    ("Never closing tasks", "Tick Done as you go; the Insights page shows completion over time."),
    ("Keeping the only copy on one laptop", "Download a backup now and then."),
]
