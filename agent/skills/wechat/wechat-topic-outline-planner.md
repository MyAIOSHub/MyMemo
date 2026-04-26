---
name: "公众号选题规划"
name_en: "Wechat Topic Planner"
description: "当用户有粗点子或资料包时使用此 skill，生成选题角度和大纲。"
description_en: "Transforms rough ideas or materials into 2-3 high-value topic angles and supporting outlines, suitable for pre-writing planning stages."
---

# Wechat Topic Outline Planner

## 目标
把模糊想法压缩成可写、可证据化、可确认的文章结构，减少后续初稿返工。

## 输入
1. 粗点子或核心主题
2. 参考资料、采访纪要、语音底稿、链接或笔记
3. 目标读者
4. 文章目标
5. 平台约束

## 工作流
1. 先整理输入，区分事实、观点、情绪和未经证实的判断。
2. 使用 `references/topic-evaluation-rubric.md` 产出 2-3 个选题角度。
3. 推荐 1 个主角度，并说明为什么比其他角度更值得写。
4. 基于主角度产出 1 套主大纲和 1 套备选大纲，使用 `references/outline-patterns.md`。
5. 对每个大纲补齐 section objective、核心论点、证据需求、转场逻辑。
6. 停在确认环节，等待用户明确确认，不写正文。

## 输出契约
1. `Input Digest`
2. `Topic Angles x2-3`
3. `Recommended Angle`
4. `Primary Outline`
5. `Backup Outline`
6. `Evidence Checklist`
7. `Waiting For Confirmation`

## 输出格式约束
- 选题名、章节名、大纲小标题默认使用陈述句，不加引号。
- 仅在直接引用原话、书名号或特定术语需要强调时使用引号。
- 避免出现“标题党式”引号堆叠，保持专业、清晰、可直接发布。

## 质量标准
- 角度之间必须真正不同，而不是同义改写。
- 大纲必须能直接交给写稿技能，不允许只有标题没有论点。
- 每个 section 只承担一个核心结论。
- 结论必须能回到用户目标，不做纯展示型结构。

## 边界
- 不写完整初稿。
- 不负责最终标题优化，标题交给 `wechat-title-generator`。
- 如果用户只说“帮我写稿”，但没有确认结构，先运行本技能。

## 参考文件
- 选题评分：`references/topic-evaluation-rubric.md`
- 大纲模式：`references/outline-patterns.md`
