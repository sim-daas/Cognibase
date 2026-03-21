# **Technical Implementation Guide: CogniBot Agentic Robotics System**

This document defines the exact software components, container topology, and integration points required to build the CogniBot system. It is the authoritative reference for Phase 1 implementation.

---

## **1. Container Topology & Networking**

CogniBot runs as two Docker containers on a single base station host. Both use `network_mode: host` to share the host network stack.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Base Station (Host Network)                                         │
│                                                                      │
│  ┌─────────────────────────────────┐  ┌────────────────────────────┐ │
│  │ Orchestrator Container          │  │ Simulation Container       │ │
│  │ (ROS2 Humble)                   │  │ (ROS2 Jazzy)               │ │
│  │                                 │  │                            │ │
│  │  PydanticAI Agent (Python)      │  │  Gazebo (gz-sim)           │ │
│  │    ├─ ReAct Loop                │  │  Nav2 Stack                │ │
│  │    ├─ MCP Client (stdio)────────┤──│─►rosbridge_server (:9090)  │ │
│  │    ├─ Skill Loader              │  │  TurtleBot3 Nodes          │ │
│  │    └─ State Cache (Phase 1B)    │  │                            │ │
│  │                                 │  │                            │ │
│  │  MCP Adapter (Node.js subprocess│) │                            │ │
│  │    └─ rosbridge transport ──────┤──│─►ws://localhost:9090       │ │
│  │                                 │  │                            │ │
│  │  rclpy Thread (Phase 1B)────────┤──│─►CycloneDDS topics        │ │
│  └─────────────────────────────────┘  └────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

### Docker Compose (Phase 1A)

```yaml
services:
  orchestrator:
    build:
      context: .
      dockerfile: Dockerfile.orchestrator
    image: cognibot/orchestrator:humble
    network_mode: host
    environment:
      - ROS_DOMAIN_ID=0
      - RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
    volumes:
      - ./skills:/app/skills
      - ./config:/app/config
    depends_on:
      - simulation

  simulation:
    build:
      context: ./agenticros
      dockerfile: docker/Dockerfile.ros2
    image: agenticros/ros2:latest
    network_mode: host
    environment:
      - ROS_DOMAIN_ID=0
      - TURTLEBOT3_MODEL=burger
      - GAZEBO_MODEL_PATH=/opt/ros/jazzy/share/turtlebot3_gazebo/models
```

### Networking Rules

- **Phase 1 (rosbridge):** The MCP adapter uses `rosbridge` transport (WebSocket to `ws://localhost:9090`). A `rosbridge_server` node must be running on the robot or on the base station and reachable over the network. The Docker Compose setup runs rosbridge in a sidecar container on the base station (`network_mode: host`).
- **Phase 1B (rclpy):** The `rclpy` aggregation thread communicates over CycloneDDS directly using `network_mode: host` and `cyclonedds.xml` with the robot peer address. Domain ID is `184`.
- **Phase 2 (local DDS):** Transport switches to `local` mode (rclnodejs direct DDS). A single `agenticros.json` config change — no code modifications required.

---

## **2. The MCP Adapter (Node.js / AgenticROS)**

The MCP adapter is a Node.js process that the Python orchestrator spawns as a **subprocess via stdio**. It uses the `agenticros-claude-code` package from the `agenticros` repository, which implements the Model Context Protocol (MCP) server. Despite its name, it is agent-platform-agnostic — any MCP client can consume its tools.

### Source Package

`agenticros/packages/agenticros-claude-code` — MCP server using `@modelcontextprotocol/sdk` with `StdioServerTransport`.

### Config (`config/agenticros.json`)

Two supported transport modes:

**Phase 1 — rosbridge** (active, tested):
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
    "maxLinearVelocity": 0.5,
    "maxAngularVelocity": 1.0
  }
}
```

**Phase 2 — local DDS** (rclnodejs, once DDS peer discovery is confirmed):
```json
{
  "transport": { "mode": "local" },
  "local": { "domainId": 184 },
  "robot": {
    "name": "CogniBot",
    "namespace": "",
    "cameraTopic": "/camera/image_raw/compressed"
  },
  "safety": {
    "maxLinearVelocity": 0.5,
    "maxAngularVelocity": 1.0
  }
}
```

### Exposed MCP Tools

| Tool | Description | ROS2 Mechanism |
|------|-------------|----------------|
| `ros2_list_topics` | List all topics and their types | rosapi service call |
| `ros2_publish` | Publish to a topic (e.g., `/cmd_vel`) | Topic publisher |
| `ros2_subscribe_once` | Get next message from a topic | One-shot subscriber |
| `ros2_service_call` | Call a ROS2 service | Service client |
| `ros2_action_goal` | Send goal to an action server (Nav2) | Action client |
| `ros2_param_get` | Get a node parameter | Parameter service |
| `ros2_param_set` | Set a node parameter | Parameter service |
| `ros2_camera_snapshot` | Capture one frame from camera topic | Subscriber + image decode |
| `ros2_depth_distance` | Distance in meters from depth camera | Depth topic subscriber |

### Build (inside Orchestrator container)

```bash
cd /app/agenticros
pnpm install && pnpm --filter @agenticros/core build && pnpm --filter @agenticros/claude-code build
```

---

## **3. The Orchestrator (Python / PydanticAI)**

This is the custom Python application that acts as the cognitive brain of CogniBot. It connects an LLM to the MCP adapter and manages all reasoning, tool dispatch, and context.

### Component A: MCP Client Module

- **Library:** `mcp` Python SDK (`pip install mcp`)
- **Function:** Spawns the MCP adapter Node.js process as a subprocess. Captures `stdout`/`stdin` to facilitate JSON-RPC tool discovery and execution via `mcp.client.stdio`.

```python
from mcp.client.stdio import stdio_client, StdioServerParameters

server_params = StdioServerParameters(
    command="node",
    args=["/app/agenticros/packages/agenticros-claude-code/dist/index.js"],
    env={"AGENTICROS_CONFIG_PATH": "/app/config/agenticros.json"}
)

async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        # Register tools with PydanticAI agent
```

### Component B: Dynamic Context Manager (Skill Loader)

- **Boot Scraper Module:** A startup script that recursively iterates through the `/app/skills` directory. Extracts the `SKILL_ID` and `DESCRIPTION` metadata from every `.md` file header.
- **Index Generator:** Compiles extracted descriptions into a numbered skill index string.
- **System Prompt Compiler:** Concatenates `SOUL.md` + the Skill Index. This forms the static, immutable system prompt for PydanticAI.
- **`load_skill_context` Tool:** A native PydanticAI `@tool`. Accepts a `skill_id`, reads the corresponding `.md` file from disk, and returns the raw content to the LLM. This allows on-demand context loading without bloating the permanent system prompt.

### Component C: High-Frequency Aggregation Layer (Phase 1B)

- **Background Thread:** A native Python `rclpy` thread running **completely outside** the PydanticAI ReAct loop.
- **CycloneDDS:** Connects directly via DDS (not through the MCP adapter). The Orchestrator container has ROS2 Humble installed, so `rclpy` works natively.
- **State Cache:** Subscribes to high-frequency topics (`/tf`, `/odom`, `/scan`, `/camera/image`). Continuously overwrites a thread-safe dictionary with the latest values.
- **`query_state` Tool:** A native PydanticAI `@tool` that reads from the State Cache and returns a formatted JSON summary to the LLM.
- **Event Interrupts:** For critical anomalies, the background thread injects a forced observation into the PydanticAI prompt queue, triggering immediate re-evaluation.

**Rule:** High-frequency data (30Hz camera, 10Hz odometry) must **never** be fed directly into the ReAct loop. The LLM only sees discrete, text-based summaries via `query_state`.

### Component D: The PydanticAI Agent

- **LLM Provider:** Provider-agnostic via PydanticAI's model abstraction. Supported:
  - **Gemini** (default) — `google-gla:gemini-2.0-flash`
  - **Ollama** (local) — `ollama:llama3.2`
  - **Groq** (free cloud) — `groq:llama-3.3-70b-versatile`
- **Initialization:**
  1. Load the System Prompt (SOUL.md + Skill Index)
  2. Register native Python tools (`load_skill_context`, `query_state`)
  3. Discover and register MCP tools from the adapter (wrapping each as a PydanticAI tool)
- **ReAct Loop:** Handles user input, invokes tools via stdio to the MCP adapter or internally, and manages prompt truncation to prevent token exhaustion.

---

## **4. Execution Pipeline: Async Navigation (Nav2)**

```
User: "Go to the kitchen"
  │
  ▼
PydanticAI Agent (ReAct)
  │  Validates intent, maps "kitchen" to coordinates via semantic memory
  ▼
MCP Client (stdio) ──► MCP Adapter (Node.js)
  │                      │  Serializes as rosbridge JSON
  │                      ▼
  │                    rosbridge_server (:9090)
  │                      │  Translates to ROS2 Action Goal
  │                      ▼
  │                    Nav2 Action Server (navigate_to_pose)
  │                      │
  ◄──────────────────────┘  Returns: { "status": "accepted" }
  │
  │  Agent continues reasoning (not blocked)
  │  Periodically calls ros2_subscribe_once on /navigate_to_pose/_action/feedback
  │
  ▼
Goal SUCCEEDED / ABORTED → Agent updates context and reports result
```

**Key Principle:** The MCP adapter's `ros2_action_goal` tool returns immediately after the action server accepts the goal. The orchestrator must poll for completion — it is never blocked waiting for navigation to finish.

---

## **5. Skill Documents (Existing)**

These `.md` files in `/app/skills` are loaded by the Dynamic Context Manager:

| Skill ID | File | Purpose |
|----------|------|---------|
| `emergency_escalation` | `Emergency Escalation.md` | Fall detection, security breach, hazard triage protocols |
| `obstacle_resolution` | `Obstacle Resolution.md` | Blocked path classification and resolution (dynamic/debris/impassable) |
| `visual_search` | `Visual Search Heuristics.md` | Systematic spatial search when object location is unknown |

---

## **6. File Structure (Phase 1A Target)**

```
Cognibase/
├── docker-compose.yml              # Two-container orchestration
├── Dockerfile.orchestrator          # ROS2 Humble + Python + Node.js
├── agenticros/                      # 3rd-party MCP adapter (submodule)
│   └── packages/
│       ├── core/                    # Transport layer (rosbridge/local/zenoh)
│       └── agenticros-claude-code/  # MCP server (stdio)
├── cognibot/                        # Custom Python orchestrator
│   ├── agent.py                     # PydanticAI agent + ReAct loop
│   ├── mcp_client.py               # MCP stdio client wrapper
│   ├── skill_loader.py             # Boot scraper + index generator
│   ├── state_cache.py              # rclpy aggregation (Phase 1B)
│   └── config.py                   # LLM provider + runtime config
├── config/
│   ├── agenticros.json             # MCP adapter transport config
│   └── cyclonedds.xml              # DDS network config
├── skills/                          # Skill documents (.md)
│   ├── SOUL.md                     # System identity & directives
│   ├── Emergency Escalation.md
│   ├── Obstacle Resolution.md
│   └── Visual Search Heuristics.md
└── docs/                            # Project documentation
```