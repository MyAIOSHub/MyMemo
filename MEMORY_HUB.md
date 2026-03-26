# Memory Hub

## Start

1. Export the model keys you actually use, or copy values from [memory-hub.env.example](/Users/chauncey2025/Documents/MyMeMo/memory-hub.env.example).
2. The default memory stack now uses DashScope for `LLM`, `embedding`, and `rerank`. In the common setup, `LLM_API_KEY`, `VECTORIZE_API_KEY`, and `RERANK_API_KEY` can all use the same Bailian key.
3. `VECTORIZE_BASE_URL` defaults to `https://dashscope.aliyuncs.com/compatible-mode/v1` with `text-embedding-v4`.
4. `RERANK_BASE_URL` defaults to `https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank` with `qwen3-rerank`.
5. Run `docker compose up --build`.
6. Open `http://127.0.0.1:1995/cc/` for Claude Code history, or `http://127.0.0.1:1995/docs` for EverMemOS.

## Endpoints

- `http://127.0.0.1:1995/api/v1/*` -> EverMemOS
- `http://127.0.0.1:1995/local-store/*` -> MyAttention-local-store
- `http://127.0.0.1:1995/cc/*` -> cchistory

## Claude Code Sync

- `cchistory` scans `${HOME}/.claude/projects` automatically after startup.
- Manual sync: `POST /cc/api/sync/run`
- Import one session: `POST /cc/api/session/{session_id}/import`
- Status: `GET /cc/api/sync/status`

## MCP

- Merge the example from [.claude/mcp-servers.memory-hub.example.json](/Users/chauncey2025/Documents/MyMeMo/.claude/mcp-servers.memory-hub.example.json) into your real `~/.claude/mcp-servers.json`.
- The MCP server exposes `search_memories` and `recent_memories`, both backed by `http://127.0.0.1:1995/api/v1`.
