# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Stack Overview

This repo has **two distinct layers** that run in separate containers:

| Layer | Language | Location | Role |
|-------|----------|----------|------|
| **AgenticROS** | TypeScript | `agenticros/` | MCP server — bridges AI tools → ROS2 topics |
| **CogniBot** | Python | `cognibot/` | Orchestrator — PydanticAI agent + skill loader |

CogniBot spawns the MCP adapter as a subprocess and wraps its tools as PydanticAI tools. The MCP adapter connects to ROS2 via rosbridge (WebSocket) or Zenoh.

## Development Commands

### TypeScript packages (AgenticROS MCP adapter)
```bash
cd agenticros
pnpm install
pnpm build        # builds all packages
pnpm typecheck    # type-check without emitting
pnpm lint         # lint all packages
```

### Python orchestrator (CogniBot)
```bash
# From host (requires Docker running):
docker compose up

# Inside the orchestrator container:
python -m cognibot.main              # Full interactive mode
python -m cognibot.main --dry-run    # Validate config + skills, no LLM/MCP

# With custom env file:
python -m cognibot.main --config /path/to/config.env
```

### Docker
```bash
docker compose up              # Start both orchestrator + rosbridge containers
docker compose up --build      # Rebuild before starting
docker compose down            # Stop
./run_dev.sh                   # Attach to or create the remote env container
```

## Architecture

### Data flow
```
User input (CLI)
    ↓
CogniBot (Python/PydanticAI) — agent.py, main.py
    ├── MCPBridge spawns: node .../agenticros-claude-code/dist/index.js
    │       ↓
    │   AgenticROS MCP adapter (TypeScript)
    │       ├── ros2_publish, ros2_subscribe_once, ros2_list_topics, ...
    │       └── Transport → rosbridge (ws://localhost:9090) or Zenoh
    ↓
ROS2 DDS bus → /cmd_vel, /odom, /camera, ...
```

### Transport modes (`agenticros.json`)
- `mode: "rosbridge"` — WebSocket to rosbridge_server (requires `rosbridge` container)
- `mode: "local"` — Direct DDS, same machine
- `mode: "zenoh"` — Via Zenoh RMW
- `mode: "webrtc"` — WebRTC for cloud/remote

### Two skill systems
1. **AgenticROS skills** (`agenticros/docs/skills.md`) — TypeScript npm packages with `"agenticrosSkill": true"`. Register tools via the OpenClaw plugin API. Installed via `skillPackages` or `skillPaths` in `agenticros.json`.
2. **CogniBot skill documents** (`skills/*.md`) — Markdown files with `SKILL_ID:` / `DESCRIPTION:` headers. Scanned at startup by `skill_loader.py`, loaded on-demand via `load_skill_context` tool. Current skills: Navigation, Emergency Escalation, Obstacle Resolution, Visual Search Heuristics.

### Config files
- `config/agenticros.json` — Transport mode, ROS bridge URL, robot namespace, safety limits
- `config/cognibot.env` — LLM provider/model, API keys, paths to skills dir, soul, MCP script
- `config/cyclonedds.xml` — DDS domain configuration

## Key Files

| File | Purpose |
|------|---------|
| `agenticros/CLAUDE.md` | Full AgenticROS documentation |
| `cognibot/agent.py` | PydanticAI agent factory + MCP tool wrappers |
| `cognibot/mcp_client.py` | Subprocess bridge to MCP adapter |
| `cognibot/skill_loader.py` | Skill index scanner + system prompt compiler |
| `cognibot/config.py` | Env-based config loader |
| `skills/SOUL.md` | System identity / robot ethics for PydanticAI agent |
| `agenticros/docs/architecture.md` | Deployment modes A/B/C/D with diagrams |
| `agenticros/docs/skills.md` | How to write TypeScript skills |
| `agenticros/SOUL.md` | AgenticROS identity when running as OpenClaw plugin |
| `docker-compose.yml` | Two-container stack (orchestrator + rosbridge) |

## MCP Server (Claude Code integration)

The MCP adapter at `packages/agenticros-claude-code/` exposes ROS2 tools as an MCP server. MCP config lives in `.mcp.json` at the agenticros root — use absolute paths to `dist/index.js`. The Python bridge reads this config and spawns the node process with `AGENTICROS_CONFIG_PATH` set.

## Testing Without a Robot

Use `--dry-run` to validate config and skill loading without connecting to ROS2 or an LLM. Set `COGNIBOT_LLM_PROVIDER=ollama` with `OLLAMA_BASE_URL` pointing to any OpenAI-compatible endpoint.
