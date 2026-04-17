# AgenticROS / CogniBot — System Architecture

> **Current phase:** TurtleBot3 Burger running ROS 2 Humble.
> Transport: **rosbridge WebSocket** (Mode B / local network).
> LLM: configurable (NVIDIA NIM or Ollama-served local model).

---

## High-Level Overview

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
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  System Prompt = SOUL.md + Skill Index (compiled at startup)  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────┐  ┌────────────────────────────────┐   │
│  │  NATIVE PYTHON TOOLS     │  │  MCP-PROXIED ROS TOOLS         │   │
│  │  (registered on agent)   │  │  (discovered via MCPBridge)    │   │
│  │                          │  │                                │   │
│  │  load_skill_context      │  │  See: MCP Tool Registry below  │   │
│  │  query_semantic_memory   │  │                                │   │
│  │  store_memory            │  │                                │   │
│  │  delete_memory           │  │                                │   │
│  │  plan_memory_route       │  │                                │   │
│  └──────────┬───────────────┘  └────────────────┬───────────────┘   │
│             │                                   │                   │
│             ▼                                   ▼                   │
│  ┌──────────────────────┐    ┌──────────────────────────────────┐   │
│  │  SemanticMemoryStore │    │  MCPBridge → stdio subprocess     │   │
│  │  (LanceDB + Ollama   │    │  agenticros-claude-code adapter   │   │
│  │   nomic-embed-text)  │    │                                  │   │
│  └──────────────────────┘    └────────────────┬─────────────────┘   │
└───────────────────────────────────────────────┼─────────────────────┘
                                                │ JSON-RPC (stdio)
                                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  AGENTICROS MCP ADAPTER                             │
│          agenticros/packages/agenticros-claude-code                 │
│                       src/tools.ts                                  │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                   MCP TOOL REGISTRY                         │    │
│  │                                                             │    │
│  │  Discovery / Introspection                                  │    │
│  │    ros2_list_topics    ros2_list_services                   │    │
│  │    ros2_list_actions   ros2_list_nodes                      │    │
│  │                                                             │    │
│  │  State Snapshot                                             │    │
│  │    ros2_query_state    (odom + /scan 8-sector radar)        │    │
│  │    ros2_subscribe_once (single message from any topic)      │    │
│  │                                                             │    │
│  │  Motion                                                     │    │
│  │    ros2_publish         (raw Twist / any msg)               │    │
│  │    ros2_cmd_vel_duration (velocity for N seconds @ 10 Hz)  │    │
│  │    ros2_action_goal     (Nav2 NavigateToPose / WaypointFollower) │
│  │                                                             │    │
│  │  Configuration                                              │    │
│  │    ros2_param_get   ros2_param_set                          │    │
│  │    ros2_service_call                                        │    │
│  │                                                             │    │
│  │  Perception                                                 │    │
│  │    ros2_camera_snapshot  (compressed / raw → base64 → TUI) │    │
│  │    ros2_vla_query        (camera → NVIDIA NIM VLM)          │    │
│  │    ros2_depth_distance   (depth image → center distance m)  │    │
│  └──────────────────────────────┬──────────────────────────────┘    │
│                                 │                                   │
│  ┌──────────────────────────────▼──────────────────────────────┐    │
│  │              SAFETY VALIDATOR  (src/safety.ts)              │    │
│  │  · rejects publish if velocity > configured limits          │    │
│  │  · blocked topic list                                       │    │
│  │  · sandbox workspace bounds                                 │    │
│  └──────────────────────────────┬──────────────────────────────┘    │
│                                 │                                   │
│  ┌──────────────────────────────▼──────────────────────────────┐    │
│  │               TRANSPORT ADAPTER  (src/transport.ts)         │    │
│  │  getTransport() → RosbridgeTransport (WebSocket 9090)       │    │
│  └──────────────────────────────┬──────────────────────────────┘    │
└────────────────────────────────-┼───────────────────────────────────┘
                                  │ rosbridge protocol (ws://)
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           ROS 2 LAYER                               │
│                     rosbridge_server  (port 9090)                   │
│                                                                     │
│                        ROS 2 DDS Bus                                │
│  /cmd_vel  /odom  /scan  /camera/image_raw/compressed               │
│  /camera/camera/depth/image_rect_raw  /battery_state               │
│  /node_manager/status  /node_manager/alert                          │
│  /start_node  /kill_node  /navigate_to_pose  ...                    │
│                                                                     │
│  ┌──────────────────┐  ┌─────────────────┐  ┌────────────────────┐  │
│  │  NodeManager     │  │  Nav2 Stack      │  │  Robot Hardware    │  │
│  │  (node_manager   │  │  (navigate_to_   │  │  Motors / LIDAR /  │  │
│  │   .py ROS node)  │  │   pose, etc.)    │  │  Camera / IMU      │  │
│  │                  │  │                  │  │                    │  │
│  │  /start_node  ◄──│  │  /navigate_to_   │  │  TurtleBot3 Burger │  │
│  │  /kill_node   ◄──│  │   pose           │  │  max 0.22 m/s      │  │
│  │  /status  ──────►│  │  /scan_for_       │  │  2.84 rad/s        │  │
│  │  /alert   ──────►│  │   objects         │  │                    │  │
│  └──────────────────┘  └─────────────────┘  └────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Component Deep-Dives

### 1. CogniBot Agent (`cognibot/agent.py`)

The agent is built on **PydanticAI** and wired at startup by `create_agent()`:

1. **System prompt compilation** — `compile_system_prompt()` reads `SOUL.md` and
   appends a skill index from all `skills/*.md` files. The result is injected as
   the static system prompt for the entire session.

2. **MCP tool wrapping** — `MCPBridge.get_tools()` returns the list of tools
   advertised by the AgenticROS MCP adapter. Each is wrapped via
   `_make_mcp_tool_fn()` into a PydanticAI `Tool.from_schema()` object that:
   - Logs calls to `stderr` and the Rich TUI panel.
   - Notifies the TUI via `tui_on_tool_start / tui_on_tool_end` hooks.
   - Saves base64 images to `/tmp/` and opens them with `feh`.
   - Appends a full entry to `AgentDeps.tool_call_log` (used by the TUI).

3. **Native tools** — Registered with `@agent.tool` directly:

   | Tool | Purpose |
   |------|---------|
   | `load_skill_context` | Loads a skill `.md` file into context by ID |
   | `query_semantic_memory` | Similarity search in LanceDB |
   | `store_memory` | Persist a new embedding to LanceDB |
   | `delete_memory` | Remove a stale fact from memory |
   | `plan_memory_route` | Multi-domain memory query for route planning |

4. **LLM model selection** — Reads `config.llm_provider`. If `"nvidia"`, wraps
   the model in `OpenAIChatModel` pointed at `https://integrate.api.nvidia.com/v1`.
   Otherwise passes the model string directly to PydanticAI (supports Ollama, etc.).

---

### 2. MCP Tool Registry (`src/tools.ts`)

All tools are implemented as cases inside `handleToolCall()` and exported in the
`TOOLS` array. Current tool set:

#### Discovery & Introspection
| Tool | Key behaviour |
|------|--------------|
| `ros2_list_topics` | Lists active topics; truncated at 50 |
| `ros2_list_services` | Lists active services; truncated at 50 |
| `ros2_list_actions` | Lists active action servers; truncated at 50 |
| `ros2_list_nodes` | Calls `/rosapi/nodes` service, returns node names |

#### State Snapshot
| Tool | Key behaviour |
|------|--------------|
| `ros2_query_state` | Parallel-fetches `/odom`, `/scan`, `/cmd_vel`; converts LIDAR array into 8-sector obstacle radar (Front, Front_Left, Left, Back_Left, Back, Back_Right, Right, Front_Right) with min-distance per sector |
| `ros2_subscribe_once` | One-shot subscription with configurable timeout; large payloads (>8 000 chars) are truncated |

#### Motion
| Tool | Key behaviour |
|------|--------------|
| `ros2_publish` | Generic topic publisher; passes through safety validator; rewrites `/cmd_vel` UUID namespacing |
| `ros2_cmd_vel_duration` | Publishes Twist at **10 Hz** for `duration` seconds then sends zero-velocity stop |
| `ros2_action_goal` | Sends Nav2 action goal; returns result asynchronously |

#### Configuration
| Tool | Key behaviour |
|------|--------------|
| `ros2_param_get` | Calls `<node>/get_parameters` service |
| `ros2_param_set` | Calls `<node>/set_parameters` service |
| `ros2_service_call` | Generic synchronous service call |

#### Perception
| Tool | Key behaviour |
|------|--------------|
| `ros2_camera_snapshot` | Subscribes to compressed or raw image topic; returns base64 + MIME type as an MCP image content block |
| `ros2_vla_query` | Auto-captures a frame then POSTs to **NVIDIA NIM** (`nvidia/nemotron-nano-12b-v2-vl`) with the operator's prompt; returns natural-language description |
| `ros2_depth_distance` | Samples the **centre region** of a depth image (`16UC1` / `32FC1`); returns distance in metres |

> **VLA Backend note:** `ros2_vla_query` currently uses the NVIDIA NIM API
> (`NVIDIA_API_KEY` env var required). An earlier prototype used Ollama `qwen3-vl`
> locally — this may return as a fallback option.

---

### 3. Node Manager (`cognibot/node_manager.py`)

A **ROS 2 node** (`/node_manager`) that acts as a dynamic process supervisor for
CV/perception pipeline scripts stored in `$PIPELINES_DIR` (default `/app/pipelines`).

```
Agent                ROS 2 Bus                NodeManager
  │                     │                          │
  │  publish /start_node│                          │
  │  {"name":"yolo-det"}│─────────────────────────►│  subprocess.Popen(yolo-det.py)
  │                     │                          │
  │                     │◄─ /node_manager/status ──│  {"running":["yolo-det"], "available":[...]}
  │  subscribe /status  │                          │
  │◄────────────────────│                          │
  │                     │                          │
  │  publish /kill_node │                          │
  │  {"name":"yolo-det"}│─────────────────────────►│  process.terminate()
  │                     │                          │
  │                     │◄─ /node_manager/status ──│  {"running":[], "available":[...]}
```

Key behaviours:
- Accepts **JSON** (`{"name": "yolo-det"}`) or **plain string** on `/start_node` and `/kill_node`.
- Normalises node names to lower-kebab-case (`yolo-det` not `YOLO_DET`).
- Publishes `/node_manager/status` every **2 s** and on every start/stop.
- Publishes `/node_manager/alert` with error details on crash or failed start.
- Graceful shutdown on `SIGINT` / `SIGTERM` — terminates all children.

---

### 4. Semantic Memory (`cognibot/memory.py`)

Persistent vector store backed by **LanceDB** with embeddings from
**Ollama `nomic-embed-text`** (dim = 768).

Four isolated tables (one per domain):

| Domain | Content |
|--------|---------|
| `spatial` | Waypoints, known obstacles, building layout |
| `behavioral` | Operator preferences, past interaction outcomes |
| `env_context` | Time-of-day patterns, crowd density, maintenance windows |
| `policy` | Custom safety rules and operational constraints |

**Write path:** `store_memory` → `_embed()` (Ollama `/api/embeddings`) → PyArrow batch → `lancedb.AsyncTable.add()`

**Read path:** `query_semantic_memory` / `plan_memory_route` → `_embed()` → `vector_search(cosine).limit(n)` → `[MemoryResult]`

Memory is consumed by:
- `query_semantic_memory` — direct domain search.
- `plan_memory_route` — cross-domain (spatial + behavioral + env_context + policy)
  search to produce a structured route plan before Nav2 navigation.

---

### 5. Safety Validator (`src/safety.ts`)

Called before every `ros2_publish` and `ros2_cmd_vel_duration`. Checks:
- Linear velocity does not exceed `config.safety.maxLinearVelocity`
- Angular velocity does not exceed `config.safety.maxAngularVelocity`
- Target topic is not in the blocked-topic list
- Pose coordinates are within optional workspace bounds

Returns `{ block: true, blockReason: "..." }` to abort the publish.

---

### 6. Skill System (`cognibot/skill_loader.py`)

Skills are Markdown files under `skills/`. Each has a YAML front-matter with
`name` and `description`. The agent has two interactions with skills:

1. **At startup** — `compile_system_prompt()` builds a skill index (name +
   description only) appended to `SOUL.md`. This gives the LLM awareness of
   available skills without loading full content.

2. **On demand** — `load_skill_context(skill_id)` loads the full skill `.md`
   into the agent's context window when a complex task requires it (e.g.
   `NODE_MANAGER`, `navigation`, `visual_search`, `SEMANTIC_MEMORY`).

---

## Data Flow Example — "Find the red bottle and navigate to it"

```
Operator TUI                CogniBot Agent                  ROS 2 / Robot
    │                            │                               │
    │  "Find the red bottle"     │                               │
    │──────────────────────────► │                               │
    │                            │ load_skill_context("visual_search")
    │                            │ ros2_list_topics()             │
    │                            │                               │
    │                            │ ros2_vla_query(prompt="Is there a red bottle? Where?")
    │                            │──────────────────────────────►│ (cam frame → NVIDIA NIM)
    │                            │◄── "Red bottle on the left"   │
    │                            │                               │
    │                            │ ros2_query_state()             │
    │                            │◄── {odom, 8-sector radar}     │
    │                            │                               │
    │                            │ plan_memory_route("red bottle area")
    │                            │◄── spatial memories + policy  │
    │                            │                               │
    │                            │ ros2_action_goal("/navigate_to_pose", goal={x,y})
    │                            │──────────────────────────────►│ Nav2 planning
    │                            │◄── {success: true}            │
    │                            │                               │
    │                            │ store_memory("spatial", "Red bottle at x=1.2,y=0.7", {label:"red_bottle"})
    │                            │                               │
    │  "Found it! Navigated."    │                               │
    │◄───────────────────────────│                               │
```

---

## Deployment Modes

AgenticROS supports four transport modes. The active mode for CogniBot on TurtleBot3
is currently **Mode B (local network, rosbridge WebSocket)**.

| Mode | Transport | Latency | Use Case |
|------|-----------|---------|----------|
| A — Same Machine | rclnodejs (local DDS) | ~ms | Edge / embedded |
| **B — Local Network** | WebSocket → rosbridge (port 9090) | ~ms | **Dev / lab (current)** |
| C — Cloud / Remote | WebRTC + STUN/TURN | 10–100ms | Production fleet |
| D — Zenoh | zenoh-ts → Zenoh router | ~ms | Zenoh RMW deployments |

### Transport Abstraction

```
MCP Tools (ros2_publish, ros2_subscribe_once, ...)
      │
      ▼
getTransport(): RosTransport
      │
      ├── RosbridgeTransport  ← ACTIVE (Mode B)
      │     └── WebSocket (ws://localhost:9090) → rosbridge_server → ROS 2 DDS
      │
      ├── LocalTransport      (Mode A — rclnodejs, stub)
      ├── WebRTCTransport     (Mode C — stub)
      └── ZenohTransport      (Mode D — zenoh-ts)
```

---

## Environment Variables (Key)

| Variable | Used By | Purpose |
|----------|---------|---------|
| `NVIDIA_API_KEY` | `ros2_vla_query` | NVIDIA NIM API auth |
| `OLLAMA_URL` | `SemanticMemoryStore` | Embedding endpoint (default `http://localhost:11434`) |
| `PIPELINES_DIR` | `NodeManager` | Directory of CV pipeline scripts (default `/app/pipelines`) |
| `LLM_MODEL` | `CogniBotConfig` | Model string for PydanticAI |
| `LLM_PROVIDER` | `CogniBotConfig` | `"nvidia"` or `"ollama"` |
| `ROSBRIDGE_URL` | Transport | rosbridge WebSocket URL |
