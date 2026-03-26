# Configuration Guide

**📍 This file has moved!**

All configuration documentation has been consolidated into the new documentation structure.

👉 **[Read the Configuration Guide](docs/5-CONFIGURATION/index.md)**

---

## Quick Links

- **AI Provider Setup** → [AI Providers](docs/5-CONFIGURATION/ai-providers.md)
- **Environment Variables Reference** → [Environment Reference](docs/5-CONFIGURATION/environment-reference.md)
- **Database Configuration** → [Database Setup](docs/5-CONFIGURATION/database.md)
- **Server Configuration** → [Server Settings](docs/5-CONFIGURATION/server.md)
- **Security Setup** → [Security Configuration](docs/5-CONFIGURATION/security.md)
- **Reverse Proxy** → [Reverse Proxy Setup](docs/5-CONFIGURATION/reverse-proxy.md)
- **Advanced Tuning** → [Advanced Configuration](docs/5-CONFIGURATION/advanced.md)

---

## What You'll Find

The new configuration documentation includes:

- **Complete environment variable reference** with examples
- **Provider-specific setup guides** for OpenAI, Anthropic, Google, Groq, Ollama, and more
- **Production deployment configurations** with security best practices
- **Reverse proxy examples** for Nginx, Caddy, Traefik
- **Database tuning** for performance optimization
- **Troubleshooting guides** for common configuration issues

---

For all configuration details, see **[docs/5-CONFIGURATION/](docs/5-CONFIGURATION/index.md)**.

---

## Memory Hub Integration (Optional)

Memory Hub connects Open Notebook to EverMemOS, allowing users to browse, search, and import personal memories as Sources.

| Variable | Required? | Default | Description |
|----------|-----------|---------|-------------|
| `MEMORY_HUB_URL` | No | `http://localhost:1995` | Memory Hub service address for connecting to EverMemOS |
| `MEMORY_HUB_USER_ID` | No | `mymemo_user` | EverMemOS user ID used for querying and importing memories |

**Note**: Memory Hub is an optional service. When it is not running or unreachable, memory-related features are automatically hidden in the UI. No configuration is needed if you do not use Memory Hub.
