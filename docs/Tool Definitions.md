# CogniBot — Tool Inventory

Complete inventory of all tools available to the CogniBot agent. Tools are divided into two categories: **MCP tools** (implemented in TypeScript, proxied via the MCP adapter) and **native Python tools** (registered directly on the PydanticAI agent).

---

## MCP Tools (AgenticROS Adapter)

These tools are defined in `agenticros/packages/agenticros-claude-code/src/tools.ts` and discovered at startup via the MCP protocol. They communicate with ROS 2 through the rosbridge WebSocket transport.

### Discovery & Introspection

| Tool | Description | ROS 2 Mechanism |
|------|-------------|-----------------|
| `ros2_list_topics` | List all active topics and message types (truncated at 50) | rosapi |
| `ros2_list_services` | List all active services (truncated at 50) | rosapi |
| `ros2_list_actions` | List all available action servers and types (truncated at 50) | rosapi |
| `ros2_list_nodes` | List all active ROS 2 nodes | `/rosapi/nodes` service |

### State Snapshot

| Tool | Description | ROS 2 Mechanism |
|------|-------------|-----------------|
| `ros2_query_state` | Aggregated robot state: odometry, 8-sector LIDAR radar, last cmd_vel. Parallel fetch from `/odom`, `/scan`, `/cmd_vel` | Multi-topic subscriber |
| `ros2_subscribe_once` | One-shot subscription returning next message from any topic. Payloads >8000 chars are truncated | One-shot subscriber |

### Motion

| Tool | Description | ROS 2 Mechanism |
|------|-------------|-----------------|
| `ros2_publish` | Generic topic publisher with safety validation and UUID namespace rewriting | Topic publisher |
| `ros2_cmd_vel_duration` | Sustained velocity command at 10 Hz for N seconds, then auto-stops with zero velocity | Timed publisher |
| `ros2_action_goal` | Send a goal to Nav2 action servers (`/navigate_to_pose`, etc.) | Action client |

### Configuration

| Tool | Description | ROS 2 Mechanism |
|------|-------------|-----------------|
| `ros2_param_get` | Read a parameter from a live ROS 2 node | `<node>/get_parameters` service |
| `ros2_param_set` | Modify a parameter on a live ROS 2 node | `<node>/set_parameters` service |
| `ros2_service_call` | Generic synchronous service call with arbitrary args | Service client |

### Perception

| Tool | Description | ROS 2 Mechanism |
|------|-------------|-----------------|
| `ros2_camera_snapshot` | Capture a single frame (compressed or raw) and return as base64 image | One-shot subscriber |
| `ros2_vla_query` | Auto-capture camera frame → NVIDIA NIM VLM inference → natural language description | Subscriber + NVIDIA API |
| `ros2_depth_distance` | Sample centre region of depth image and return distance in metres | Depth subscriber |

---

## Native Python Tools (PydanticAI Agent)

These tools are registered directly on the PydanticAI agent in `cognibot/agent.py`. They run in-process and do not go through the MCP adapter.

### Skill System

| Tool | Description |
|------|-------------|
| `load_skill_context` | Load the full instruction document for a skill by its ID. Returns raw Markdown content for procedural guidance |

### Task Planning & Mission Control

| Tool | Description |
|------|-------------|
| `create_task_plan` | Mandatory first step for complex missions. Decomposes a goal into discrete milestones and required ROS 2 nodes |
| `yield_status` | Pause the cognitive loop and yield execution to Mission Control. Used after completing milestones, waiting on hardware, or hitting blocks |

### Semantic Memory

| Tool | Description |
|------|-------------|
| `query_semantic_memory` | Similarity search against persistent LanceDB memory (spatial, behavioral, env_context, policy domains) |
| `store_memory` | Embed and persist a new fact to a memory domain with optional metadata tags |
| `delete_memory` | Remove an outdated memory entry by its UUID (must query first to find the ID) |
| `plan_memory_route` | Cross-domain memory query (spatial + behavioral + env_context + policy) to produce a structured route plan before navigation |

---

## Adding New Tools

To add a new tool to the system:

1. **Define the interface** — Add the tool schema to the `TOOLS` array in `agenticros/.../src/tools.ts`
2. **Implement logic** — Add a case in the `handleToolCall` switch statement
3. **Rebuild** — `pnpm --filter @agenticros/claude-code build` (inside the orchestrator container)
4. **Auto-discovery** — CogniBot auto-discovers the new tool via MCP at next startup

For native Python tools, register them with `@agent.tool` in `cognibot/agent.py`.


## **Navigation & Movement**

1. **Maps\_to\_point**: Drive the robot to a specified spatial coordinate (x, y, theta) using Nav2.  
2. **initiate\_auto\_docking**: Override current tasks and navigate to the charging station.  
3. **track\_object**: Lock navigation and camera pan/tilt to follow a specific bounding box or ID.

## **Vision & Perception**

4. **capture\_camera\_frame**: Request a single RGB image matrix from the primary camera.  
5. **get\_3d\_depth**: Query the point cloud for the exact distance to a specific coordinate or object.  
6. **detect\_objects\_coco**: Run 2D bounding box inference for common standard objects (returns coordinates/labels).  
7. **filter\_color\_hsv**: Isolate and return bounding boxes for specific objects based on a defined HSV color spectrum.  
8. **query\_vla\_pipeline**: Send an image and a natural language query to the Vision-Language-Action model for abstract visual reasoning.  
9. **read\_text\_ocr**: Extract written text and digits from the current visual frame.  
10. **scan\_qr\_code**: Decode QR or ArUco markers in the environment for localization or data retrieval.

## **State & Kinematics**

11. **estimate\_pose**: Extract human skeletal joint coordinates from the current camera frame.  
12. **recognize\_action**: Analyze sequential frames/poses to identify human behaviors (e.g., falling, running).  
13. **read\_temperature**: Poll thermal sensors for ambient or specific hardware surface temperatures.  
14. **classify\_audio\_event**: Identify non-speech sounds (e.g., breaking glass, alarms, footsteps) via the microphone array.

## **Interaction & Communication**

15. **ask\_human\_clarification**: Synthesize text-to-speech to physically ask the operator a question via the robot's speakers.  
16. **send\_notification**: Dispatch a text message or alert payload to the human operator's device.  
17. **trigger\_alarm**: Activate physical or digital emergency sirens and strobes on the robot or facility network.  
18. **control\_appliance**: Toggle smart home devices, doors, or lab equipment via IoT relays.

## **Memory & Context**

19. **query\_semantic\_memory**: Retrieve historical context, prior states, or mapped locations from the localized LanceDB database.
20. **store\_memory**: Store a new entry in the robot's persistent semantic memory (spatial, behavioral, env_context, policy) for future reference.
21. **plan\_memory\_route**: Query spatial and behavioral memory for a preferred route to a specific named destination before initiating Nav2.
22. **delete\_memory**: Remove a specific outdated or conflicting fact from semantic memory by its unique ID.