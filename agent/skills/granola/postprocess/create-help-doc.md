---
name: "创建帮助文档"
name_en: "Create Help Doc"
description: "使用关于某个功能的会议记录来创建面向客户的帮助文章。"
description_en: "Use the transcript from this meeting about a feature to create a customer-facing help article."
phase: postprocess
trigger: ["/create-help-doc", "help article", "customer doc"]
---

# Create Help Doc — Customer-Facing Article

Use the transcript from this meeting about a feature to create a customer-facing help article.

## Steps

1. From the transcript, infer the **feature name** and give a 1–2 sentence description of what it does.
   - First reply: confirm inferred feature name + basic functionality. Ask if I'd like to provide a style guide or example article for format/tone.
   - Wait for my confirmation before drafting.

2. When drafting the article, include:
   - **What the feature does** and **why it's useful** (1–3 short sentences)
   - **Set-up guidance** if required (otherwise skip)
   - **Step-by-step instructions** for how to use the feature
   - **Troubleshooting** only if common user issues are likely; skip if not
   - Exclude all internal notes, technical jargon, or details irrelevant to end users

3. At the bottom, add: **Recommended screenshots:** [list of screenshots that would help]

## Output Format
- Polished help article: headings, short paragraphs, bullet lists for steps
- Concise, actionable, easy to scan
