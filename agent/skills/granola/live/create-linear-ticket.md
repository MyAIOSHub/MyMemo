---
name: "创建线性工单 — 从会议讨论"
name_en: "Create Linear Ticket — From Meeting Discussion"
description: "根据此会议记录（或显式命令 /create-linear-ticket）帮我创建一个 Linear 工单。建议应创建的工单，与我确认后，生成一个可打开并预填信息的 Linear 问题链接。"
description_en: "Help me create a Linear ticket from this meeting transcript (or from explicit /create-linear-ticket commands). Suggest what ticket should be created, confirm with me, then generate a valid markdown link that opens a pre-filled Linear issue."
phase: live
trigger: ["/create-linear-ticket", "linear issue", "file a ticket"]
---

# Create Linear Ticket — From Meeting Discussion

Help me create a Linear ticket from this meeting transcript (or from explicit `/create-linear-ticket` commands). Suggest what ticket should be created, confirm with me, then generate a valid markdown link that opens a pre-filled Linear issue.

If I invoke `/create-linear-ticket` and provide context, bypass transcript analysis and use my input as the source of truth.

## Linear URL Schema

Base URL: `https://linear.new`
Parameters:
- `title` → issue title (URL-encoded, use `+` for spaces)
- `description` → markdown supported; URL-encoded; use `%0A` for line breaks
- `assignee` → UUID, display name, or `assignee=me`
- `priority` → Urgent, High, Medium, Low
- `status`, `estimate`, `labels` (comma-separated), `project`, `cycle`, `links`

## Workflow

1. **Suggest** what ticket(s) should be created.
   - Usually just one. Keep it short: one-line title + one sentence of context.
   - Ask "sounds right?"

2. **Incorporate feedback** if I push back.

3. **Generate clickable markdown link** named `Create Linear Ticket`.
   - Properly URL-encode all parameters.
   - Always include a **title**.
   - Include description, labels, priority, assignee, project if obvious.

4. **Description sections** (only if explicitly in transcript):
   - **Customer Impact** — affected customers, user count, account value
   - **Steps to Reproduce** — numbered list
   - **Expected vs Actual**
   - **Environment** — browser, device, OS, version
   - **Business Impact** — lost revenue, blocked workflow, severity
   - **Workaround** — temporary fix
   - **Links** — support ticket, Slack thread, external doc

   ➡️ If not in transcript, **do not invent**. Omit the section.

5. Always return as valid markdown link. Example:
   `[Create Linear Ticket](https://linear.new?title=Password+reset+error&description=Customer+cannot+reset+passwords.%0A%0ACustomer+Impact%3A+Reported+by+3+enterprise+accounts.&labels=bug,backend&priority=High)`

6. Placeholder issues → mark in title: `[Placeholder] Draft ticket for ...`

7. Never use `"` quotation marks; always use `'` instead.
