# Memory Hub MCP Server

MCP server that connects AI coding agents (Claude Code, Cline, Claude Desktop) to the [EverCore (EverOS)](https://github.com/EverMind-AI/EverOS) Memory Hub for long-term memory.

## Tools

| Tool | Description |
|------|-------------|
| `search_memories` | Semantic/keyword/hybrid search across episodic memories |
| `browse_memories` | Paginated listing by memory type (episodic, profile, etc.) |
| `store_memory` | Save a message as a new memory |
| `check_hub_status` | Verify Memory Hub connectivity |

## Prerequisites

- Memory Hub running at `http://localhost:1995` (see parent project's `docker-compose.memory-hub.yml`)
- Python 3.10+ with `uv`

## Configuration

### Claude Code

Add to `~/.claude/settings.json` (global) or `.claude/settings.json` (project):

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

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

### VS Code (Cline / MCP-compatible extensions)

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
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

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMORY_HUB_URL` | `http://localhost:1995` | EverCore Memory Hub gateway URL |
| `MEMORY_HUB_USER_ID` | `mymemo_user` | Default user ID for memory operations |

## Development

```bash
# Install dependencies
uv sync

# Run directly
uv run memory-hub-mcp

# Test with MCP inspector
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | uv run memory-hub-mcp
```
