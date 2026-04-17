# **CogniBot — Demo Video Use Cases**

> These are showcase scenarios built entirely from **currently implemented tools**. Each demo is self-contained, progressively complex, and chosen to maximize visual impact for recording.

---

## **Tool Inventory (What's Actually Live)**

| Layer | Implemented Tools |
|---|---|
| **MCP / ROS2** | `ros2_list_topics`, `ros2_list_services`, `ros2_list_actions`, `ros2_list_nodes`, `ros2_publish`, `ros2_subscribe_once`, `ros2_service_call`, `ros2_action_goal`, `ros2_param_get`, `ros2_param_set`, `ros2_camera_snapshot`, `ros2_vla_query`, `ros2_depth_distance`, `ros2_cmd_vel_duration`, `ros2_query_state` |
| **Native Python** | `load_skill_context`, `query_semantic_memory`, `store_memory`, `delete_memory`, `plan_memory_route` |
| **NodeManager (via ROS topics)** | `obj-detector` (COCO detection via `/start_node`, `/kill_node`, `/node_manager/status`) |

---

## **Demo 1 — "Eyes Open" (VLM Spatial Reasoning)**

**Difficulty:** Beginner | **Duration:** ~2 min recording

### Prompt
> `"Look around and tell me what you can see. Take a snapshot too."`

### Tool Chain
1. `ros2_query_state` — Get obstacle radar + odometry snapshot
2. `ros2_camera_snapshot` — Deliver image to TUI (opens in `feh`)
3. `ros2_vla_query` — Describe scene in natural language using `nvidia/nemotron-nano-12b-v2-vl`

### Why This Demo Works
- Shows the **VLM pipeline end-to-end** in under 3 tool calls
- The TUI renders the image inline + the agent speaks a description — visually impressive for a first-time viewer
- No navigation risk — robot is stationary

### What to Highlight in Recording
- The `📷 IMAGE: VIEW CAPTURE` link appearing in the TUI
- The VLA model output describing scene objects, colors, and spatial layout
- The LIDAR radar grid from `ros2_query_state` (Front/Back/Left/Right distances)

---

## **Demo 2 — "Object Hunt" (Node Manager + COCO Detection)**

**Difficulty:** Intermediate | **Duration:** ~3 min recording

### Prompt
> `"Use the object detector and tell me what objects you can see right now."`

### Tool Chain
1. `ros2_subscribe_once` on `/node_manager/status` — Discover available pipelines
2. `ros2_publish` to `/start_node` with `{"name": "obj-detector"}` — Launch COCO detector
3. `ros2_subscribe_once` on `/node_manager/status` — Verify node moved to `"running"`
4. `ros2_subscribe_once` on `/det` (or equivalent output topic) — Read detection results
5. `ros2_vla_query` — Cross-validate with VLM: "Do you see any of these: [list from COCO]?"
6. `ros2_publish` to `/kill_node` — Clean shutdown

### Why This Demo Works
- Shows the **Node Manager lifecycle** from discovery → start → consume → stop
- COCO output is concrete (bounding boxes, labels, confidence scores) — easy to understand on screen
- VLM cross-validation adds an "AI reasoning" layer beyond raw detection

### What to Highlight in Recording
- The agent autonomously checking `available` list before starting
- Detection blob appearing in the TUI tool output panel
- Agent confirming the node is actually running before consuming data (the mandatory verification step)
- Clean kill at the end — the agent does not leave nodes running

---

## **Demo 3 — "Memory That Sticks" (Semantic Memory Learning Loop)**

**Difficulty:** Intermediate | **Duration:** ~4 min recording  
**Recommended: Record in two parts (store session, then recall session)**

### Part A — Teaching the Robot (Session 1)
**Prompt:**
> `"Remember that the charging dock is in the top-left corner of the room at approximately x=1.5, y=2.0."`

#### Tool Chain
1. `store_memory(domain="spatial", content="Charging dock is located at x=1.5, y=2.0, top-left corner of room.", metadata={"label": "charging_dock", "x": 1.5, "y": 2.0})`
2. `store_memory(domain="policy", content="Always navigate to charging dock when battery is low.", metadata={"trigger": "low_battery"})`

### Part B — Using the Knowledge (Session 2)
**Prompt:**
> `"Take me to the charging dock."`

#### Tool Chain
1. `plan_memory_route(destination_label="charging dock")` — Queries all 4 memory domains
2. Agent reads waypoint `x=1.5, y=2.0` from returned plan
3. `ros2_action_goal` to `/navigate_to_pose` with recalled coordinates
4. `store_memory(domain="behavioral", content="Successfully navigated to charging dock.")` — Closes the learning loop

### Why This Demo Works
- Demonstrates **persistent, cross-session intelligence** — the robot gets smarter over time
- The contrast between "told once" and "recalled autonomously later" is visually compelling
- Shows all 4 memory domains in action (spatial, behavioral, env_context, policy)

### What to Highlight in Recording
- The `plan_memory_route` output returning the previously stored waypoint verbatim
- The agent reasoning aloud: "I found coordinates from spatial memory, using navigate_through_poses"
- The `store_memory` call after success — showing the robot updating its own knowledge base

---

## **Demo 4 — "Autonomous Scout" (Nav + VLM + Memory Integration)**

**Difficulty:** Advanced | **Duration:** ~5 min recording

### Prompt
> `"Drive to coordinates (1.0, 0.5), look around when you arrive, describe what you see, and remember the location with a name."`

### Tool Chain
1. `plan_memory_route(destination_label="1.0, 0.5")` — Check if we've been there before
2. `ros2_action_goal` to `/navigate_to_pose` — Drive to target
3. `ros2_query_state` — Post-arrival state check (confirm position via odometry)
4. `ros2_vla_query` — Visual description of arrival location
5. `ros2_camera_snapshot` — Archive the view for the user
6. `store_memory(domain="spatial", ...)` — Name and store the location based on what was seen
7. `store_memory(domain="behavioral", ...)` — Record navigation success

### Why This Demo Works
- This is the **full closed-loop spatial mapping workflow** from conversation history (conv `71838eab`)
- The robot autonomously names locations based on visual context — not hard-coded labels
- Shows all three major capability pillars: **Nav + VLM + Memory** in one sequence

### What to Highlight in Recording
- The Nav2 action goal being dispatched and the robot physically moving
- VLM output describing the scene ("I can see a desk, a whiteboard, and a fire extinguisher")
- Agent autonomously labeling: "I'll store this as 'office area' based on what I saw"
- The resulting memory entry with visual metadata attached

---

## **Demo 5 — "Robot Doctor" (Telemetry + Parameter Tuning)**

**Difficulty:** Beginner–Intermediate | **Duration:** ~2 min recording

### Prompt
> `"What is the robot's current state? Check its sensors, position, and any nearby obstacles."`

### Tool Chain
1. `ros2_query_state` — Full radar view: Front/Back/Left/Right/diagonal obstacle distances + odometry + cmd_vel
2. `ros2_subscribe_once` on `/battery_state` — Get battery level
3. `ros2_list_nodes` — Show active subsystems
4. Agent synthesizes a natural-language health report

### Optional Extension (Parameter Tuning)
**Prompt:**
> `"The robot seems slow. Check its max speed and increase it by 20%."`

5. `ros2_param_get(node="/controller_server", parameter="max_vel_x")` — Read current value
6. `ros2_param_set(node="/controller_server", parameter="max_vel_x", value=<new_value>)` — Apply change

### Why This Demo Works
- Shows **diagnostic capability** without any movement — safe to demo in any environment
- The 8-directional radar output is visually interesting and easy to explain
- Parameter tuning via natural language feels like magic to a non-technical audience

### What to Highlight in Recording
- The LIDAR radar grid showing meters to obstacles in real-time
- Agent explaining what each metric means in plain English
- Live parameter change taking effect without restarting any node

---

## **Demo 6 — "Two-Command Robot" (Natural Language to Physical Action)**

**Difficulty:** Beginner | **Duration:** ~1 min recording  
**Best for: Social media clips or project summaries**

### Prompt
> `"Move forward a bit, then spin around."`

### Tool Chain
1. `ros2_cmd_vel_duration(linear_x=0.1, angular_z=0.0, duration=2.0)` — Forward 2 seconds
2. `ros2_cmd_vel_duration(linear_x=0.0, angular_z=1.5, duration=2.0)` — Spin 2 seconds

### Why This Demo Works
- Requires **zero infrastructure** — no Nav2, no map, no sensors
- Immediate, unambiguous physical result visible on camera
- Perfect "intro clip" to establish the core concept: text → robot action

### What to Highlight in Recording
- Agent reasoning in TUI: "I'll use ros2_cmd_vel_duration with linear_x for forward motion"
- Robot physically moving as described
- Zero latency between command and action

---

## **Demo 7 — "See and Remember" (VLM + Node Manager + Memory)**

**Difficulty:** Advanced | **Duration:** ~4-5 min recording**  
**Power Demo — combines all three unique capabilities**

### Prompt
> `"Start the object detector, look around, and store everything you find as spatial memories so you remember what's in this room."`

### Tool Chain
1. `ros2_subscribe_once` on `/node_manager/status` — Discover `obj-detector`
2. `ros2_publish` to `/start_node` — Launch COCO detector
3. `ros2_subscribe_once` on `/det` — Get COCO detections (labels + bounding boxes)
4. `ros2_vla_query` — Ask VLM: "Describe the position and context of each detected object"
5. For each detected object: `store_memory(domain="spatial", ...)` — Store object location with semantic description
6. `ros2_publish` to `/kill_node` — Clean shutdown
7. Agent summarizes: "I've mapped N objects in this room into spatial memory"

### Why This Demo Works
- Shows **autonomous knowledge acquisition** — the robot maps its own environment without being told what to find
- Fuses structured data (COCO bounding boxes) with semantic reasoning (VLM descriptions)  
- After this demo, Demo 4's navigation recall will find these stored locations

### What to Highlight in Recording
- Detection results flowing in from the `obj-detector` node
- VLM adding semantic context to raw bounding box data
- Each `store_memory` call building the spatial knowledge base entry by entry
- Final summary showing the count of learned objects

---

## **Recording Tips**

| Tip | Detail |
|---|---|
| **Split TUI + Robot view** | Use a split screen: TUI on left (showing tool calls), robot camera or Gazebo sim on right |
| **Show the skill loader** | Start any demo by saying a relevant phrase — watch `load_skill_context` fire automatically |
| **Use the tool call panel** | The yellow `🛠️ Tool Call` panels in the TUI are visually distinctive — ensure they're visible |
| **Show image receipts** | When `ros2_camera_snapshot` fires, the `📷 IMAGE: VIEW CAPTURE` link appears — click it live |
| **Run in sim first** | Test all demos in Gazebo simulation before recording with the physical robot |
| **Narrate the ReAct loop** | Pause recording at each tool call and explain the agent's reasoning aloud |
