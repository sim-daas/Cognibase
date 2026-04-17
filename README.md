<p align="center">
  <h1 align="center">🤖 CogniBot — Agentic Robotics Orchestrator</h1>
  <p align="center">
    <em>An LLM-driven cognitive layer that turns natural language into autonomous robot behaviour.</em>
  </p>
</p>

<p align="center">
  <a href="#architecture">Architecture</a> •
  <a href="#quickstart">Quickstart</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#tool-inventory">Tools</a> •
  <a href="#skill-system">Skills</a> •
  <a href="#development">Development</a>
</p>

---

## Overview

**CogniBot** is a fully autonomous robotic control system that connects a Large Language Model (LLM) to a physical robot via ROS 2. It receives natural-language commands from a terminal UI, reasons about them using an agentic ReAct loop, and executes multi-step missions by chaining robotic tools — navigation, perception, memory, and dynamic CV pipelines — all without human micro-management.

**Key Capabilities:**

- 🧠 **Agentic Reasoning** — PydanticAI-powered ReAct loop with configurable LLM backends (Gemini, NVIDIA NIM, Ollama, Groq)
- 🗺️ **Autonomous Navigation** — Nav2 integration with memory-biased route planning
- 👁️ **Visual Perception** — VLA model (NVIDIA NIM) for scene understanding, depth distance, camera snapshots
- 💾 **Persistent Semantic Memory** — LanceDB vector store with 4 memory domains surviving reboots
- 📋 **Task Planning** — Mandatory mission decomposition into verifiable milestones for complex actions
- 🔧 **Dynamic CV Pipelines** — Node Manager for spawning/killing DeepStream-powered perception nodes at runtime
- 🛡️ **Safety Validator** — Velocity limits, blocked topics, and workspace bounds enforcement
- 📊 **Post-Mission Review** — Automated performance analysis and skill review engine

**Hardware Target:** TurtleBot3 Burger running ROS 2 Humble (max 0.22 m/s linear, 2.84 rad/s angular).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          OPERATOR LAYER                             │
│              Terminal TUI  (cognibot/tui.py)                        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ natural-language commands
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        COGNIBOT AGENT LAYER                         │
│                    cognibot/agent.py  (PydanticAI)                  │
│                                                                     │
│  System Prompt = SOUL.md + Skill Index (compiled at startup)        │
│                                                                     │
│  ┌──────────────────────────┐  ┌────────────────────────────────┐   │
│  │  NATIVE PYTHON TOOLS     │  │  MCP-PROXIED ROS TOOLS         │   │
│  │  load_skill_context      │  │  ros2_list_topics/services/...  │   │
│  │  create_task_plan         │  │  ros2_publish / ros2_action_goal│   │
│  │  yield_status            │  │  ros2_vla_query / ros2_camera_* │   │
│  │  query_semantic_memory   │  │  ros2_query_state / ros2_depth_*│   │
│  │  store/delete_memory     │  │  ros2_cmd_vel_duration          │   │
│  │  plan_memory_route       │  │  ros2_param_get/set / ...       │   │
│  └──────────┬───────────────┘  └────────────────┬───────────────┘   │
│             │                                   │                   │
│  ┌──────────┴──────────┐    ┌───────────────────┴────────────────┐  │
│  │ SemanticMemoryStore │    │ MCPBridge → stdio subprocess       │  │
│  │ (LanceDB + Ollama)  │    │ agenticros-claude-code adapter     │  │
│  └─────────────────────┘    └────────────────┬──────────────────┘  │
└──────────────────────────────────────────────┼─────────────────────┘
                                               │ JSON-RPC (stdio)
                                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  AGENTICROS MCP ADAPTER (Node.js)                   │
│    Safety Validator → Transport Adapter → rosbridge WebSocket       │
└──────────────────────────────────────────┬──────────────────────────┘
                                           │ ws://localhost:9090
                                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           ROS 2 LAYER                               │
│  rosbridge_server → DDS Bus → Robot Hardware (TurtleBot3 Burger)   │
│  Nav2 · NodeManager · LIDAR · Camera · Odometry · IMU              │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Summary

| Component | Location | Purpose |
|-----------|----------|---------|
| **Agent** | `cognibot/agent.py` | PydanticAI ReAct loop, tool registration, LLM wiring |
| **TUI** | `cognibot/tui.py` | Terminal UI with chat area, tool sidebar, thinking modes |
| **MCP Client** | `cognibot/mcp_client.py` | Spawns and manages the Node.js MCP adapter subprocess |
| **Config** | `cognibot/config.py` | Environment-based configuration with multi-provider LLM support |
| **Memory** | `cognibot/memory.py` | LanceDB vector store with Ollama nomic-embed-text embeddings |
| **Skill Loader** | `cognibot/skill_loader.py` | Boot-time skill scanning + on-demand context injection |
| **Review Engine** | `cognibot/review.py` | Post-mission tool call analysis and performance reports |
| **Node Manager** | `cognibot/node_manager.py` | ROS 2 process supervisor for DeepStream CV nodes |
| **MCP Adapter** | `agenticros/.../src/tools.ts` | 15 MCP tools bridging LLM → ROS 2 via rosbridge |
| **SOUL.md** | `skills/SOUL.md` | System identity, directives, and operational guidelines |

---

## Quickstart

### Prerequisites

- Docker & Docker Compose
- NVIDIA GPU with drivers (for Node Manager / DeepStream CV)
- A physical TurtleBot3 running ROS 2 Humble on DDS domain 184, **or** the Gazebo simulation stack

### 1. Clone the Repository

```bash
git clone https://github.com/<your-org>/Cognibase.git
cd Cognibase
```

### 2. Configure Environment

Copy and edit the environment config:

```bash
cp config/cognibot.env.example config/cognibot.env
# Edit config/cognibot.env with your API keys and LLM provider
```

Key variables in `config/cognibot.env`:

| Variable | Description | Example |
|----------|-------------|---------|
| `COGNIBOT_LLM_PROVIDER` | LLM backend | `gemini`, `nvidia`, `ollama`, `groq` |
| `COGNIBOT_LLM_MODEL` | Model identifier | `google-gla:gemini-2.0-flash` |
| `NVIDIA_API_KEY` | NVIDIA NIM API key (for VLA + NVIDIA provider) | `nvapi-...` |
| `GOOGLE_API_KEY` | Gemini API key | |
| `OLLAMA_BASE_URL` | Ollama endpoint | `http://localhost:11434/v1` |
| `COGNIBOT_MEMORY_EMBEDDING_URL` | Ollama instance for embeddings | `http://localhost:11434` |

Configure the ROS 2 transport in `config/agenticros.json`:

```json
{
  "transport": { "mode": "rosbridge" },
  "rosbridge": { "url": "ws://localhost:9090" },
  "robot": {
    "name": "CogniBot",
    "namespace": "",
    "cameraTopic": "/camera/image_raw/compressed"
  },
  "safety": {
    "maxLinearVelocity": 0.22,
    "maxAngularVelocity": 2.84
  }
}
```

### 3. Build and Launch

**Physical robot deployment:**

```bash
docker compose up --build
```

This starts three services:
- **`orchestrator`** — CogniBot agent (Python + Node.js MCP adapter)
- **`rosbridge`** — rosbridge_server sidecar (WebSocket ↔ DDS bridge)
- **`node_manager`** — DeepStream CV pipeline supervisor

**Simulation deployment:**

```bash
docker compose -f docker-compose.sim.yml up --build
```

### 4. Connect to the TUI

```bash
docker exec -it cognibot_orchestrator bash
source /opt/ros/humble/setup.bash
python3 -m cognibot.main --config /app/config/cognibot.env
```

### 5. Dry Run (Validate Without Connecting)

```bash
python3 -m cognibot.main --dry-run --config /app/config/cognibot.env
```

This validates configuration, scans skills, and prints the compiled system prompt without connecting to the MCP adapter or LLM.

---

## Tool Inventory

CogniBot exposes **15 MCP tools** (ROS 2 bridge) + **7 native Python tools** = **22 tools total**.

### MCP Tools (via AgenticROS Adapter)

| Category | Tools |
|----------|-------|
| **Discovery** | `ros2_list_topics`, `ros2_list_services`, `ros2_list_actions`, `ros2_list_nodes` |
| **State** | `ros2_query_state` (8-sector radar + odom), `ros2_subscribe_once` |
| **Motion** | `ros2_publish`, `ros2_cmd_vel_duration`, `ros2_action_goal` |
| **Config** | `ros2_param_get`, `ros2_param_set`, `ros2_service_call` |
| **Perception** | `ros2_camera_snapshot`, `ros2_vla_query` (NVIDIA NIM VLM), `ros2_depth_distance` |

### Native Python Tools

| Tool | Purpose |
|------|---------|
| `load_skill_context` | On-demand loading of skill instruction documents |
| `create_task_plan` | Mandatory mission decomposition for complex tasks |
| `yield_status` | Context-clearing yield to Mission Control |
| `query_semantic_memory` | Semantic similarity search across memory domains |
| `store_memory` | Persist new facts to vector memory |
| `delete_memory` | Remove outdated memory entries |
| `plan_memory_route` | Cross-domain route planning with memory integration |

See [docs/Tool Definitions.md](docs/Tool%20Definitions.md) for full documentation.

---

## Skill System

Skills are Markdown documents in `skills/` that provide procedural instructions for complex tasks. They are **not loaded into the system prompt** — only a summary index is included. The full skill text is loaded on-demand via `load_skill_context(skill_id)`.

### Available Skills

| Skill ID | File | Purpose |
|----------|------|---------|
| `navigation` | `Navigation.md` | Nav2 goal formatting, pose checking, memory-biased routing |
| `NODE_MANAGER` | `NodeManager.md` | Spawning/killing DeepStream CV nodes via ROS 2 topics |
| `SEMANTIC_MEMORY` | `Semantic Memory.md` | Memory CRUD operations, domain guidelines, route planning |
| `emergency_escalation` | `Emergency Escalation.md` | Fall detection, hazard triage, visual verification protocol |
| `obstacle_resolution` | `Obstacle Resolution.md` | Blocked path classification (Human/Pushable/Static) |
| `visual_search` | `Visual Search Heuristics.md` | Systematic waypoint-based search for lost objects |

### Creating a New Skill

1. Create a Markdown file in `skills/` with this header format:
   ```markdown
   ## **SKILL_ID: my_skill DESCRIPTION: What this skill does.**
   ```
2. Write procedural instructions including tool usage examples
3. CogniBot detects it automatically at startup and adds it to the skill index

---

## Semantic Memory

CogniBot maintains a persistent vector memory (LanceDB + Ollama `nomic-embed-text`) across four domains:

| Domain | Content | Example |
|--------|---------|---------|
| `spatial` | Waypoints, obstacles, routes | "Charging dock at x=1.5, y=2.0" |
| `behavioral` | Operator preferences, past outcomes | "Operator prefers slow speed near lab" |
| `env_context` | Time patterns, crowd density | "Corridor B crowded weekday mornings" |
| `policy` | Safety rules, constraints | "Never drive near wet floor zone" |

Memory survives container restarts via a Docker named volume (`cognibot_memory`).

---

## Configuration

### LLM Providers

| Provider | Model String | Notes |
|----------|-------------|-------|
| Gemini | `google-gla:gemini-2.0-flash` | Default, requires `GOOGLE_API_KEY` |
| NVIDIA NIM | `meta/llama-4-maverick-17b-128e-instruct` | Requires `NVIDIA_API_KEY` |
| Ollama | `ollama:llama3.2` | Local, requires `OLLAMA_BASE_URL` |
| Groq | `groq:llama-3.3-70b-versatile` | Free cloud, requires `GROQ_API_KEY` |

### Transport Modes

| Mode | Config | Use Case |
|------|--------|----------|
| **rosbridge** (active) | `"mode": "rosbridge"` | Dev/lab via WebSocket to port 9090 |
| local DDS | `"mode": "local"` | Edge deployment with rclnodejs |

---

## Project Structure

```
Cognibase/
├── cognibot/                        # Python orchestrator
│   ├── agent.py                     # PydanticAI agent + tool registration
│   ├── config.py                    # Environment-based configuration
│   ├── main.py                      # CLI entry point + TUI launcher
│   ├── mcp_client.py               # MCP stdio client lifecycle
│   ├── memory.py                    # LanceDB semantic memory store
│   ├── node_manager.py             # ROS 2 CV pipeline supervisor
│   ├── review.py                    # Post-mission analysis engine
│   ├── skill_loader.py             # Boot-time skill scanner
│   └── tui.py                      # Textual terminal UI
├── agenticros/                      # MCP adapter (TypeScript)
│   └── packages/
│       ├── core/                    # Transport layer (rosbridge/local/zenoh)
│       └── agenticros-claude-code/  # MCP server with 15 ROS 2 tools
│           └── src/tools.ts
├── skills/                          # Skill documents (Markdown)
│   ├── SOUL.md                     # System identity & directives
│   ├── Navigation.md
│   ├── NodeManager.md
│   ├── Semantic Memory.md
│   ├── Emergency Escalation.md
│   ├── Obstacle Resolution.md
│   └── Visual Search Heuristics.md
├── config/                          # Runtime configuration
│   ├── cognibot.env                # LLM provider + API keys
│   ├── agenticros.json             # Transport + safety config
│   └── cyclonedds.xml              # DDS peer discovery
├── docs/                            # Project documentation
├── docker-compose.yml              # Physical robot deployment
├── docker-compose.sim.yml          # Simulation deployment
├── Dockerfile.orchestrator         # Orchestrator container
├── Dockerfile.remote               # rosbridge sidecar
└── requirements.txt                # Python dependencies
```

---

## Development

### Local Development (Without Docker)

```bash
# Install Python dependencies
pip install -r requirements.txt

# Pull the embedding model
ollama pull nomic-embed-text

# Build the MCP adapter
cd agenticros && pnpm install && pnpm run build && cd ..

# Run in dry-run mode
python -m cognibot.main --dry-run

# Run interactively (requires rosbridge_server on port 9090)
python -m cognibot.main --config config/cognibot.env
```

### Rebuilding the MCP Adapter (Inside Docker)

```bash
docker exec -w /app/agenticros cognibot_orchestrator pnpm run build
```

### Adding a New MCP Tool

1. Add schema to `TOOLS` array in `agenticros/.../src/tools.ts`
2. Add handler in `handleToolCall()` switch-case
3. Rebuild: `pnpm --filter @agenticros/claude-code build`
4. Restart CogniBot — tools are auto-discovered via MCP

### Adding a Native Python Tool

Register with `@agent.tool` in `cognibot/agent.py`:

```python
@agent.tool
async def my_tool(ctx: RunContext[AgentDeps], param: str) -> str:
    """Docstring becomes the tool description for the LLM."""
    # Implementation...
    return "result"
```

---

## Deployment Modes

| Mode | Stack | Use Case |
|------|-------|----------|
| **Physical** | `docker-compose.yml` | Real TurtleBot3 via DDS domain 184 |
| **Simulation** | `docker-compose.sim.yml` | Gazebo + Nav2 |
| **Standalone** | `run_dev.sh` | Single container for development |

---

## License

This project is proprietary. All rights reserved.
