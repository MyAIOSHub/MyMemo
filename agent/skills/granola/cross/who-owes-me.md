---
name: "谁欠我什么"
name_en: "Who Owes Me What"
description: "我工作中的人说他们今天要做什么——也就是我可能想检查的我应该收到的东西，如果他们还没发给我？"
description_en: "What are all the things people I work with said they'd do **by today** — i.e., what are the things people owe me that I might want to check up on if they haven't sent it?"
phase: cross
trigger: ["/who-owes-me-what", "who owes me", "outstanding from others"]
---

# Who Owes Me What

What are all the things people I work with said they'd do **by today** — i.e., what are the things people owe me that I might want to check up on if they haven't sent it?

**Don't include stuff I need to do.**

Output:
- Group by person
- For each: what they committed to, when (if mentioned), source meeting
- Mark as ⚠️ if past due
