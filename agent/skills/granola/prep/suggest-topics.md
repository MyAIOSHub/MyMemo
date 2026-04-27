---
name: "建议主题 — 会前准备"
name_en: "Suggest Topics — Pre-meeting Prep"
description: "我即将开会但准备时间有限，需要分析会议背景、回顾近期会议记录并生成有用的会前准备建议。"
description_en: "I'm about to have a meeting with little time to prepare. Analyze my upcoming meeting context, review my recent meeting history, and generate useful call prep notes."
phase: prep
trigger: ["/suggest-topics", "suggest topics", "prep notes", "before meeting"]
---

# Suggest Topics — Pre-meeting Prep Notes

I'm about to have a meeting and I haven't had much time to prepare for it. Analyze my upcoming meeting context, review my recent meeting history, and generate useful call prep notes.

**Steps (internal only, do not output):**
1. Confirm meeting title, time, attendees.
2. Classify meeting type from title/attendees (1:1, project sync, interview, external call, board, networking, or unknown).
3. Review recent meeting history:
   - Prioritize the last 1–2 meetings with that attendee for context.
   - Add older notes only if still active/relevant, especially for recurring meetings with similar or the same titles.
   - Include related meetings with these attendees.
   - If no related/recent meeting history is relevant, identify it as a meeting with [person] from [company name, only implied by domain — not gmail], either ask clarifying questions or make general recommendations based on meeting type and my company context.
4. For 1:1s, add role and responsibility-aware reflections or questions, not just updates.

Always respond in human-sounding language, avoid jargon.

<output_template>
[One-sentence introduction confirming the upcoming meeting name and time organically, e.g. "1:1 with Sam at 11am" or "Platform project catch-up meeting"]

**Who**
- [Skip if no external attendees.]

**Where we left off**
- One sentence recap of the last relevant interaction.

**Suggested topics**
- [2–3 scannable bullets, shaped by meeting type.]
- [Phrase as possibilities, not directives.]

[A single sentence confirming the context that informed this response, and asks if there's anything else that should be considered or if I want to add details about my goals for this meeting.]
</output_template>
