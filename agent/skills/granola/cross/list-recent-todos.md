---
name: "列出最近待办事项 — 跨会议"
name_en: "List Recent Todos — Across Meetings"
description: "展示一个简短的行动项列表，然后从最近的会议记录中提取并显示我的待办事项"
description_en: "Present a short list of action items, then extract and display my outstanding to-dos from recent meeting notes."
phase: cross
trigger: ["/list-recent-todos", "recent todos", "outstanding action items"]
---

# List Recent Todos — Across Meetings

Present a short list of action items, then extract and display my outstanding to-dos from recent meeting notes.

Add a short line before the main list: *"Here are your recent action items, organized by meeting:"*

## Date Rules
Ignore your internal date/time. Always assume "Today" is the date I provide, or if none provided, the date of my query. "Today" always means the calendar date on which I'm asking. Use that as anchor. Meetings labeled relative: "Today", "Yesterday", or weekday + date.

## Workflow
1. Analyze meeting notes in **reverse chronological order**.
2. Strict transcript filter: only process meetings where notes exist. If no notes, write "No notes generated".
3. Extract clear action items I have reasonable confidence belong to me. Err on inclusion if likely my responsibility based on my role.
4. Output format:
   - Group by day (Today, Yesterday, then weekday + date)
   - Bold meeting name (or **Unnamed Meeting**)
   - Use `*` bullets, one per item. Include implicit items.
   - If no action items: "No action items found"
5. Always show most recent calendar day. If fewer than 5 meetings, include earlier days until ≥5 meetings shown.
   - Never split a day across outputs.
   - After finishing a day (and ≥5 meetings), stop and ask: "Do you want me to keep going with previous days?"

## Action Item Definition
A future commitment I agreed to in the meeting — a task I will do after.
- "I am doing X" (current work / progress) → NOT an action item
- "I will do X" / "I'll handle X" / "Hannah to do X" → action item
- Indirect commitments ("I'll look into that", "I'll draft something") → include
- Group suggestion ("we should update docs") → include if implicitly mine
- Clearly assigned to someone else → exclude

## Format Rules
- Markdown mandatory
- Short, recognition-friendly phrasing ("Send draft contract" not "I said I'd probably send a contract at some point")
- Never `* -` or empty bullet
- If meeting has no title or "null" → "Unnamed Meeting"

## Self-check
Before final output:
- Re-read items, confirm no personal todos skipped
- Confirm no `* -` formatting errors

Begin immediately with the first meeting.
