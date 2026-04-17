# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Cognibase is an **agentic robotics control system** that uses PydanticAI as the orchestrator and a Node.js MCP server as a translation bridge to ROS2. The system controls a physical TurtleBot3 Burger robot using native ROS2 communication (CycloneDDS) over a local subnet.

## Architecture

The system consists of three layers:

1. **Agent Orchestrator** (`cognibot/`) — Python/PydanticAI agent that handles the ReAct loop, conversation memory, and dynamic skill injection
2. **Translation Bridge** (`agenticros/`) — Node.js MCP server that exposes ROS2 capabilities as JSON-RPC tools
3. **Hardware Interface** — ROS2 nodes executing on the robot (Nav2, cameras, sensors)

The orchestrator connects to the MCP adapter via stdio, which joins the CycloneDDS network and communicates with the robot.

## Repository Structure

| Path | Purpose |
|------|---------|
| `cognibot/` | Python package — agent, config, TUI, skill loader, semantic memory |
| `agenticros/` | TypeScript/Node.js MCP server — ROS2 transport, tools for Claude Code |
| `skills/` | Markdown skill files + SOUL.md (system identity) |
| `config/` | Configuration files (agenticros.json, cognibot.env, cyclonedds.xml) |
| `docker-compose.yml` | Physical robot deployment stack |
| `docker-compose.sim.yml` | Gazebo simulation stack |

## Commands

### Running CogniBot

```bash
# Full interactive TUI mode
python -m cognibot.main

# Dry-run (validate config + skills without connecting)
python -m cognibot.main --dry-run

# With custom theme
python -m cognibot.main --theme textual-dark
```

### Docker

```bash
# Physical robot stack
docker compose -f docker-compose.yml up

# Simulation stack (Gazebo)
docker compose -f docker-compose.sim.yml up

# Development shell on robot container
./run_dev.sh [image] [container_name] [repo_path]
```

### AgenticROS (TypeScript)

```bash
cd agenticros
pnpm install
pnpm typecheck
pnpm build
```

## Key Concepts

### SOUL.md (Critical)

The file `skills/SOUL.md` is the **system identity** — it defines the robot's operational parameters, safety limits, interaction style, and mandatory tool call sequences. The agent MUST follow SOUL.md directives when controlling the robot.

**Mandatory tool sequences** per SOUL.md:
- Capability queries → MUST run `ros2_list_topics` AND subscribe to `/node_manager/status`
- Visual queries → MUST call `ros2_list_topics` first, then use `ros2_vla_query` or `ros2_camera_snapshot`
- Navigation → SHOULD call `plan_memory_route` first to check semantic memory

### Skill Loading

Skills are markdown files in `skills/` with `SKILL_ID` and `DESCRIPTION` headers. At startup:
1. `skill_loader.py` scans the directory and extracts metadata
2. The skill index is compiled into the PydanticAI system prompt
3. The LLM calls `load_skill_context(skill_id)` to load full text on-demand

Available skills: NODE_MANAGER, visual_search, navigation, SEMANTIC_MEMORY (see skills/SOUL.md)

### Semantic Memory

Persistent knowledge storage using LanceDB + Ollama embeddings. Four domains:
- `spatial` — waypoints, obstacles, routes
- `behavioral` — operator preferences, interaction history
- `env_context` — time-of-day patterns, crowd conditions
- `policy` — custom safety rules

Tools: `query_semantic_memory`, `store_memory`, `delete_memory`, `plan_memory_route`

### MCP Tools

The AgenticROS MCP server exposes ROS2 tools: `ros2_publish`, `ros2_list_topics`, `ros2_camera_snapshot`, `ros2_vla_query`, `navigate_to_pose`, etc. These are wrapped as PydanticAI tools.

## Configuration

Main config file: `config/cognibot.env`
- `COGNIBOT_LLM_PROVIDER` — gemini, ollama, groq, nvidia
- `COGNIBOT_LLM_MODEL` — model string (provider-specific)
- API keys via environment variables

ROS2 config: `config/agenticros.json`
- Transport mode: "rosbridge" or "local" (native DDS)
- Robot name, camera topic, safety limits

## Important Notes

- This is a **physical robot control system** — bad commands result in collisions or equipment damage, not text errors
- The LLM cannot see images directly — use `ros2_vla_query` for semantic understanding, `ros2_camera_snapshot` for the user
- High-frequency telemetry never flows directly to the LLM — it goes through an aggregation layer
- State decays: re-verify with tools before reporting current status
- Tool call logs are maintained in the TUI for review/retrieval