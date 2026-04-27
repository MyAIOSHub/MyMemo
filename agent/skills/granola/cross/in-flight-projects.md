---
name: "查看进行中项目"
name_en: "Show In-Flight Projects"
description: "将会议记录转化为经理或负责人的一份状态概览：过去两周所有进行中的项目清单，谁负责什么，以及每个项目的成果、障碍和风险。"
description_en: "Turn meeting notes into a single status overview for a manager or lead: a complete list of all in-flight initiatives from the last 2 weeks, who is on what, and the wins, blockers, and risks for each."
phase: cross
trigger: ["/show-in-flight-projects", "in flight projects", "active initiatives"]
---

# Show In-Flight Projects — Status Overview

Turn meeting notes into a single status overview for a manager or lead: a complete list of all in-flight initiatives from the last 2 weeks, who is on what, and the wins, blockers, and risks for each.

**You must list every in-flight initiative** that appears in the notes — do not summarize, merge, or drop smaller threads. Brief someone who needs the whole board at a glance. Use only what's in the notes.

## Rules

**Timebox: last 2 weeks only.** If notes include dates, use only those within 14 days. If scoped to a time range, treat that as the window and state it in Overview ("Based on notes from 3–17 Feb."). No older-only initiatives.

**List every in-flight initiative.** Enumerate every distinct project, initiative, or workstream. Don't cherry-pick "main" items or collapse several into one. If five initiatives are mentioned, output five. Missing one is a failure. When in doubt, include it.

**Use only information from the notes.** No invented projects, owners, or status. If something isn't mentioned → "Not in notes". "In flight" = actively underway or being discussed as current; not finished or cancelled.

**Treat "project" loosely.** A named project, theme ("Q1 launch"), or recurring thread. If notes don't use clear names, infer short labels.

**One line per idea where you can.** Wins/blockers/risks → bullets or one line each. No long paragraphs.

## Format

1. **Overview** — 2–3 sentences: state this is based on last 2 weeks (or date range), total count of in-flight initiatives, overall health read.

2. **By project / initiative** — One block per initiative:
   * **Name** (short label)
   * **Who's on it** — names or roles. If unclear, "Not specified."
   * **Wins** — recent progress, shipped items, unblocks. Bullets. If none, "None in notes."
   * **Blockers** — what's stuck, waiting on, delayed. If none, "None in notes."
   * **Risks** — what could go wrong, at-risk timelines, dependencies. If none, "None in notes."

Order by importance/risk if notes suggest. Every in-flight initiative must appear.

Keep tight. Reader should scan in under 2 minutes.
