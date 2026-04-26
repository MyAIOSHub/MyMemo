---
name: "记忆检索"
name_en: "Memory Recall"
description: "从记忆库中查找与当前话题相关的历史信息。"
description_en: "Retrieve historical knowledge related to the current topic from the memory library."
---

# memory-recall

目标：从记忆库中检索与当前话题相关的历史知识。

触发条件：
- 用户提到过去的项目、决策、对话
- 需要回顾之前的技术方案或讨论结论
- 用户问"之前我们怎么做的"、"上次讨论了什么"

输出要求：
- 引用具体的历史记忆条目（含时间戳）
- 总结关键决策和上下文
- 标注记忆来源（浏览器/Claude Code/手动）
