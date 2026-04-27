---
name: "列出待办事项 — 明确与推断任务"
name_en: "List My Todos — Explicit + Inferred Action Items"
description: "列出我在此会议中的**明确指示的任务**（待办事项）和**隐含的任务**（推断出的任务）"
description_en: "List my **explicitly directed action items** (To do), and **implicit action items** (Inferred) from this meeting."
phase: postprocess
trigger: ["/list-my-todos", "list todos", "action items mine"]
---

# List My Todos — Explicit + Inferred Action Items

List my **explicitly directed action items** (To do), and **implicit action items** (Inferred) from this meeting.

Format as a bullet list. Include deadlines only where they were promised and as they relate to today's date. Prioritize by urgency.

Output:

**To do:** (short bullet list of explicitly assigned action items, with deadlines if mentioned)
**Inferred:** (bullet list, no deadlines)

This list needs to be **actionable** — don't put anything vague or generic.
