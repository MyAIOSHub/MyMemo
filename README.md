<div align="center">

# MyMemo

**Personal long-term memory infrastructure for AI agents.**

Build, store, search, and share memories across Claude Code, OpenClaw, Codex, and any agent that speaks HTTP.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/MyAIOSHub/MyMemo)](https://github.com/MyAIOSHub/MyMemo/stargazers)

</div>

---

## What is MyMemo?

MyMemo is a self-hosted memory stack that gives AI coding agents persistent, cross-session, cross-tool memory. It collects context from your daily work — browser tabs, Claude Code conversations, manual notes — processes them into searchable episodic memories via LLM extraction, and makes them available to any agent through a unified API.

```
Browser Attention + Claude Code Sessions + Manual Input
                        ↓
              EverCore Memory Hub (:1995)
         LLM extraction → embedding → indexing
                        ↓
    ┌──────────┬──────────┬──────────┬──────────┐
    │ Claude   │ OpenClaw │  Codex   │   Any    │
    │  Code    │ Context  │  HTTP    │  MCP     │
    │  Hooks   │ Engine   │  Client  │  Client  │
    └──────────┴──────────┴──────────┴──────────┘
```

## Features

- **Auto-collect** — Browser attention data (via MyAttention extension), Claude Code session transcripts (via cchistory), all continuously synced
- **LLM-powered extraction** — Raw messages → boundary detection → episode clustering → episodic memories (powered by EverCore / EverOS)
- **Hybrid search** — Keyword (Elasticsearch) + vector (Milvus + DashScope embedding) + rerank (qwen3-rerank)
- **Multi-agent access** — Claude Code hooks (auto inject/save), OpenClaw plugin (ContextEngine), MCP server (manual tools), HTTP API (universal)
- **Privacy-first** — Everything runs locally. No data leaves your machine.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Data Collection Layer                     │
│                                                              │
│  MyAttention local-store     cchistory          Manual       │
│  (browser SQLite)            (Claude Code       (API POST)   │
│      ↓ 5s poll               transcript scan)                │
│                                  ↓ 5min poll                 │
├──────────────────────────────────────────────────────────────┤
│               EverCore Memory Hub (gateway :1995)            │
│                                                              │
│  nginx gateway ─┬─ /api/v1/*    → EverCore (memorize+search)│
│                 ├─ /local-store/* → MyAttention              │
│                 └─ /cc/*         → cchistory                 │
│                                                              │
│  Infra: MongoDB · Milvus · Elasticsearch · Redis             │
├──────────────────────────────────────────────────────────────┤
│                    Agent Consumption Layer                    │
│                                                              │
│  Claude Code Hooks     MCP Server      OpenClaw Plugin       │
│  (auto inject/save)    (4 tools)       (ContextEngine)       │
│                                                              │
│  HTTP API (any agent)                                        │
│  POST /api/v1/memories         — store                       │
│  POST /api/v1/memories/search  — search                      │
│  POST /api/v1/memories/get     — browse                      │
└──────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Configure

```bash
cp memory-hub.env.example memory-hub.env
# Edit memory-hub.env — set your DashScope (Bailian) API key:
#   LLM_API_KEY=sk-your-key
#   VECTORIZE_API_KEY=sk-your-key
#   RERANK_API_KEY=sk-your-key
```

### 2. Start Memory Hub

```bash
docker compose -f docker-compose.memory-hub.yml --env-file memory-hub.env up -d
```

Verify: `curl http://localhost:1995/health`

### 3. Connect Claude Code (auto memory)

The hooks in `.claude/hooks/` auto-activate when you open this project in Claude Code:

| Hook | Trigger | What it does |
|------|---------|--------------|
| `session-context.js` | Session start | Loads 5 recent memories into context |
| `inject-memories.js` | Each prompt | Searches relevant memories, injects into context |
| `store-memories.js` | Each response | Extracts conversation, stores as new memory |

### 4. Connect via MCP (optional)

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "memory-hub": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/memory-hub-mcp", "memory-hub-mcp"],
      "env": {
        "MEMORY_HUB_URL": "http://localhost:1995",
        "MEMORY_HUB_USER_ID": "mymemo_user"
      }
    }
  }
}
```

Tools: `search_memories`, `browse_memories`, `store_memory`, `refresh_memory_docs`, `check_hub_status`

## Agent System (Claude Agent SDK)

MyMemo includes a standalone agent powered by Claude Agent SDK with **8 subagents** and **167 skills**.

### Subagents

| Subagent | Skills | Scene |
|---|---|---|
| `code-dev` | 61 | Code review, debugging, testing, architecture, full-stack |
| `project-manager` | 22 | Planning, task breakdown, git workflow, CI/CD, shipping |
| `meeting-advisor` | 19 | Decision making, Socratic questioning, risk analysis, synthesis |
| `content-creator` | 18 | Articles, WeChat, social media, copywriting, novels |
| `deep-thinker` | 16 | First principles, five whys, roundtable debate, analogies |
| `business-strategist` | 15 | Market sizing, competitive analysis, unit economics, JTBD |
| `memory-manager` | 15 | Store, recall, search, organize, generate insights |
| `learning-researcher` | 8 | Study notes, flashcards, literature review, paper analysis |

### Usage

```bash
cd agent/

# Route to a subagent
python3 agent.py -a meeting-advisor "should we use Kafka or SQS?"
python3 agent.py -a business-strategist "evaluate the AI memory assistant market"
python3 agent.py -a code-dev -s code-reviewer "review this PR"

# Direct skill
python3 agent.py -s ljg-roundtable "discuss memory architecture"

# With memory context
python3 agent.py -a project-manager "plan MyMemo v2 development"

# List all
python3 agent.py --list-subagents
python3 agent.py --list-skills
```

### Memory .md Materialization

Memories are materialized from EverCore into topic-based `.md` files for intent-driven retrieval:

```bash
# Manual refresh
cd memory-hub-mcp/ && python materializer.py

# Auto: SessionStart hook checks freshness (30min TTL) and refreshes if stale
```

Output: `memory-docs/INDEX.md` + `project-*.md` + `user-preferences.md` + `recent-focus.md`

## Agent Integration

### Claude Code — Hooks (full auto)

```
Session start → load recent memories
User prompt   → hybrid search → inject <memory> XML into context
Claude stops  → extract last turn → POST to EverCore
```

No manual action needed. Memories accumulate across sessions.

### OpenClaw — Context Engine

```
EverMemOS/examples/openclaw-plugin/
```

Install as OpenClaw plugin. Auto-recalls before each response, auto-saves after each turn.

### MCP Server — Manual tools

```
memory-hub-mcp/
```

4 tools: search, browse, store, health check. Works with Claude Code, Cline, Claude Desktop, Cursor.

### HTTP API — Universal

Any agent that can send HTTP:

```bash
# Search
curl -X POST http://localhost:1995/api/v1/memories/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"project architecture","method":"hybrid","memory_types":["episodic_memory"],"top_k":5,"filters":{"user_id":"mymemo_user"}}'

# Store
curl -X POST http://localhost:1995/api/v1/memories \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"mymemo_user","messages":[{"message_id":"m1","sender_id":"agent","sender_name":"Agent","role":"assistant","timestamp":1713200000000,"content":"Decided to use PostgreSQL for the auth service."}]}'

# Browse
curl -X POST http://localhost:1995/api/v1/memories/get \
  -H 'Content-Type: application/json' \
  -d '{"memory_type":"episodic_memory","page":1,"page_size":10,"filters":{"user_id":"mymemo_user"}}'
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| **Gateway** (nginx) | 1995 | Unified entry point for all Memory Hub services |
| **EverCore** | — | Memory engine: memorize pipeline, search, LLM extraction |
| **MyAttention** | — | Browser attention data collector (SQLite + sync) |
| **cchistory** | — | Claude Code session scanner and importer |
| **MongoDB** | — | Raw message and episode storage |
| **Milvus** | — | Vector embeddings for semantic search |
| **Elasticsearch** | — | Text index for keyword/hybrid search |
| **Redis** | — | Cache and async job queue |

All services are internal to Docker network. Only port 1995 is exposed.

## Configuration

### memory-hub.env

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `openai` | LLM provider (openai-compatible) |
| `LLM_MODEL` | `qwen-long` | Model for memory extraction |
| `LLM_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | LLM API endpoint |
| `LLM_API_KEY` | — | LLM API key |
| `VECTORIZE_PROVIDER` | `dashscope` | Embedding provider |
| `VECTORIZE_MODEL` | `text-embedding-v4` | Embedding model |
| `RERANK_PROVIDER` | `dashscope` | Rerank provider |
| `RERANK_MODEL` | `qwen3-rerank` | Rerank model |
| `TENANT_SINGLE_TENANT_ID` | `t_mymemo` | Tenant namespace for data isolation |

### Claude Code hooks env

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMORY_HUB_URL` | `http://localhost:1995` | Memory Hub gateway URL |
| `MEMORY_HUB_USER_ID` | `mymemo_user` | User ID for memory operations |

## Project Structure

```
MyMemo/
├── agent/                        # Claude Agent SDK assistant
│   ├── agent.py                  #   CLI entry — NDJSON output, subagent dispatch
│   ├── subagents.py              #   8 subagent definitions (167 skills mapped)
│   ├── requirements.txt          #   claude-agent-sdk + httpx
│   └── skills/                   #   167 skills in 16 categories
│       ├── coding/               #     code-reviewer, security-auditor, test-engineer
│       ├── meeting/              #     19 meeting analysis skills
│       ├── thinking/             #     16 deep reasoning frameworks
│       ├── engineering/          #     21 software engineering skills
│       ├── workflow/             #     15 dev workflow skills
│       ├── marketing/            #     6 business/marketing skills
│       ├── diagnosis/            #     9 diagnostic skills
│       ├── content/              #     6 content creation skills
│       ├── wechat/               #     12 WeChat publishing skills
│       ├── dev-tools/            #     26 development tools
│       ├── learning/             #     8 learning/research skills
│       ├── clawiser/             #     8 memory management skills
│       ├── insight/              #     5 insight generation skills
│       ├── commands/             #     7 command skills
│       ├── references/           #     4 checklists
│       └── memory/               #     2 memory-specific skills
├── .claude/
│   ├── hooks/                    #   Claude Code auto-memory hooks
│   │   ├── session-context.js    #     SessionStart → materialize + inject INDEX
│   │   ├── inject-memories.js    #     UserPromptSubmit → LLM intent route → read .md
│   │   └── store-memories.js     #     Stop → extract + store to EverCore
│   └── settings.json             #   Hook registration
├── memory-hub-mcp/               # MCP server (5 tools)
│   ├── memory_hub_mcp.py         #   search/browse/store/refresh/status
│   ├── materializer.py           #   EverCore → topic .md files
│   └── pyproject.toml
├── memory-docs/                  # Materialized .md files (gitignored, auto-generated)
│   ├── INDEX.md                  #   File index with summaries
│   ├── project-*.md              #   Per-project knowledge docs
│   ├── user-preferences.md       #   User profile
│   └── recent-focus.md           #   Last 3 days activity
├── EverMemOS/                    # Vendored EverCore engine (gitignored)
├── cchistory/                    # Claude Code session importer (gitignored)
├── MyAttention-local-store/      # Browser attention collector (gitignored)
├── docker-compose.memory-hub.yml # Full Memory Hub stack
├── memory-hub.env.example        # Environment template
└── MEMORY_HUB.md                 # Memory Hub documentation
```

## Powered By

- [EverMind-AI/EverOS](https://github.com/EverMind-AI/EverOS) — EverCore long-term memory engine
- [DashScope / Bailian](https://dashscope.aliyuncs.com/) — Default LLM, embedding, and rerank provider
- [Milvus](https://milvus.io/) — Vector database for semantic search
- [MongoDB](https://www.mongodb.com/) — Document storage
- [Elasticsearch](https://www.elastic.co/) — Text search engine

## License

MIT — see [LICENSE](LICENSE).
