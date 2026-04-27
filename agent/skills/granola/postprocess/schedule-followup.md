---
name: "安排跟进会议 — 日历/邮件链接"
name_en: "Schedule Follow-up Meeting — Calendar/Email Links"
description: "生成包含标题、描述、地点和时间的谷歌日历模板链接"
description_en: "Generate a Google Calendar template link with title, description, location, and time"
phase: postprocess
trigger: ["/schedule-follow-up-meeting", "schedule followup", "draft calendar invite"]
---

# Schedule Follow-up Meeting — Calendar/Email Links

## URL Schemas

### Google Calendar
`https://calendar.google.com/calendar/render?action=TEMPLATE&text=TITLE&details=DESCRIPTION&location=LOCATION&dates=START/END`
- TITLE → URL-encoded
- DESCRIPTION → optional
- LOCATION → optional
- START/END → `YYYYMMDDTHHMMSSZ` (UTC) or `YYYYMMDD` for all-day

### Gmail
`https://mail.google.com/mail/?view=cm&fs=1&to=TO&su=SUBJECT&body=BODY&cc=CC&bcc=BCC`
- TO → comma-separated recipients
- SUBJECT, BODY → URL-encoded

## Workflow

Based on meeting discussion, suggest follow-up meeting(s). Most of the time, suggest **one option** (multiple only if very different). Be extremely short — mention timeframe like "next week", but don't list all details. Ask "sounds right?". Keep responses short and fast.

If I give feedback, incorporate. Then do any of:
- Generate `[Draft email with suggested times]` link → Gmail draft. Suggest times where I'm free (use my time zone).
- Suggest times based on my calendar (mention I'm free; what's before/after each suggested slot).
- Generate `[Create calendar event]` link → Google Calendar with all metadata filled out.

## Rules
- Always return links as **clickable markdown**. Don't break formatting.
- URL-encode all calendar/gmail params.
- Placeholder events → state "placeholder" in title.
- List proposed times before generating links.
