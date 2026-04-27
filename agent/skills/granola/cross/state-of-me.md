---
name: "我的状态 — 每周汇报"
name_en: "State of Me — Weekly Manager Update"
description: "为直属下属生成一份每周的「我的状态」更新，以易于浏览的方式呈现障碍、重点任务和未来议题，提升透明度，避免意外，并确保获得认可。"
description_en: "Generate a weekly **State of Me** update for a direct report to share with their manager. Surface blockers, priorities, and forward-looking topics in a **scannable way** that builds visibility, prevents surprises, and ensures recognition."
phase: cross
trigger: ["/state-of-me", "weekly state", "manager update"]
---

# State of Me — Weekly Manager Update

Generate a weekly **State of Me** update for a direct report to share with their manager. Surface blockers, priorities, and forward-looking topics in a **scannable way** that builds visibility, prevents surprises, and ensures recognition.

## Instructions
- Analyze the **past two business weeks**
- Always produce **three numbered sections**: **1. Blockers I need help with**, **2. My current priorities**, **3. On my mind**
- Bullets, short verb-first lines
- Use the person's own words where possible
- If uncertain → tag `[PLEASE VERIFY: detail]`
- If inferred → tag `[INFERRED: basis]`
- If any tags exist, append a **⚠️ Review** section
- Concise, written for human reading
- **Prioritize most recent 5 business days** for blockers/priorities/thoughts
- Include older items (up to 2 weeks) only if active/unresolved/relevant
- Drop completed/outdated context
- Highlight **new developments since last update**

## Date Handling
- Anchor to today
- Normalize meeting references ("today", "yesterday", weekday → actual calendar date)
- Tasks/blockers > 7 business days ago likely done unless they reappear
- Prioritize freshness

## Context Rules
- Weight internal meetings (1:1s, standups, reviews) more than external calls
- Always include manager meetings if present
- Synthesize across conversations where manager wasn't present
- For external calls, include if relevant to blockers/priorities

## Section Guidelines

**1. Blockers I need help with** — look for "blocked, stuck, waiting on, dependency, approval". Specify **who can help** + **by when** if possible.

**2. My current priorities** — active projects/initiatives, progress, milestones, deadlines. Highlight if decision/action needed from manager.

**3. On my mind** — forward-looking: early risks, upcoming PTO, team/process notes. Keep phrasing close to person's own language.

## Default Email Output

**Subject:** Weekly update – [Current week dates]

Hi [Manager name],

**1. Blockers I need help with:**
- [Blocker 1: description + WHO + WHEN]
- [Blocker 2: …] [PLEASE VERIFY/INFERRED if applicable]

**2. My current priorities:**
- [Project/initiative]: [Progress + milestone/deadline]

**3. On my mind:**
- [Topic 1: forward-looking issue, risk, or idea]

Thanks,
[my name]

**⚠️ Review** (only if tags exist):
- [PLEASE VERIFY: item] – [explanation]
