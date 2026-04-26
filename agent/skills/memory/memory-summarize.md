---
name: "记忆摘要"
name_en: "Memory Summary"
description: "将当前对话的关键信息提炼为可存储的记忆。"
description_en: "Extracts key information from the current conversation into storable memory."
---

# memory-summarize

目标：将当前对话的关键信息提炼为可存储的记忆。

触发条件：
- 对话中产生了重要决策或技术方案
- 用户明确要求"记住这个"
- 会话即将结束

输出要求：
- 一段结构化摘要（含主题、决策、行动项）
- 标注涉及的项目名称
- 提取关键技术细节（架构、API、配置变更等）
