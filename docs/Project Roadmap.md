# **Project Roadmap: CogniBot — Agentic Robotics System**

## **Phase 1A: Physical Robot & Core Pipeline** ✅

**Objective:** Validate the end-to-end agentic pipeline against the physical TurtleBot3 using rosbridge as the transport. Prove that a PydanticAI orchestrator can drive the robot through natural language via the MCP adapter bridge, with dynamic skill loading and Nav2 execution.

**Container Topology:**

| Container | Base Image | Role |
|-----------|-----------|------|
| **Orchestrator** (ROS2 Humble) | `osrf/ros:humble-desktop-full` | PydanticAI agent + MCP adapter (Node.js subprocess). Manages the ReAct loop, LLM API calls, skill injection, and MCP client. |
| **rosbridge sidecar** | `osrf/ros:humble-desktop-full` | Runs `rosbridge_server` on port 9090, bridging the MCP adapter WebSocket to the physical robot's DDS network. |

**Transport:** `rosbridge` — the MCP adapter connects via WebSocket (`ws://localhost:9090`). The rosbridge sidecar runs in host network mode and talks to the physical TurtleBot3 via CycloneDDS (DDS domain 184, peer `192.168.0.25`). For full physical operation, use `docker-compose.physical.yml`.

**Milestones:**

1. **Docker Compose Standup:** ✅ Build the orchestrator container. Verify rosbridge WebSocket connectivity from the MCP adapter to the rosbridge sidecar (or robot-hosted rosbridge). Confirm the physical TurtleBot3 is discoverable on DDS domain 184.
2. **MCP Adapter Integration:** ✅ Build and configure the MCP adapter (`agenticros/packages/agenticros-claude-code`) inside the Orchestrator container. Verify tool discovery — the Python MCP client must successfully list all ROS2 tools (`ros2_list_topics`, `ros2_publish`, `ros2_subscribe_once`, `ros2_service_call`, `ros2_action_goal`, `ros2_param_get`, `ros2_param_set`, `ros2_camera_snapshot`, `ros2_cmd_vel_duration`).
3. **PydanticAI Orchestrator Build:** ✅ Implement the custom Python agent using PydanticAI. Wire the ReAct loop, register MCP-discovered tools as PydanticAI tools, and configure LLM provider (Ollama local default, with provider-agnostic support for Gemini/Groq).
4. **Skill Pipeline Validation:** ✅ Implement the Boot Scraper and Dynamic Context Manager. Verify the system prompt is correctly compiled from `SOUL.md` + Skill Index. Test that the LLM can call `load_skill_context` to pull full skill documents on demand.
5. **Nav2 Proof:** Issue a navigation goal via the `ros2_action_goal` MCP tool to the physical TurtleBot3. Verify successful point-to-point navigation and status reporting.

**Exit Criteria:** The LLM autonomously navigates the physical TurtleBot3 via natural language commands, dynamically loads skill documents, and executes Nav2 goals.

---

## **Phase 1B: Telemetry & State Aggregation**

**Objective:** Add the high-frequency telemetry aggregation layer. Enable the orchestrator to maintain a real-time state cache of the robot's environment and respond to critical event interrupts.

**Milestones:**

1. **rclpy Background Thread:** Implement a Python `rclpy` thread inside the Orchestrator container, running entirely outside the PydanticAI ReAct loop. This thread subscribes to high-frequency ROS2 topics over CycloneDDS (`/tf`, `/odom`, `/scan`, `/camera/image`).
2. **State Cache:** Build a thread-safe dictionary that the background thread continuously updates with the latest sensor values. Expose a `query_state` PydanticAI `@tool` that reads from the cache and returns a formatted summary to the LLM.
3. **Event Interrupt System:** Implement a forced-observation injection mechanism. When the background thread detects a critical anomaly (e.g., collision, object detected), it pushes an interrupt into the PydanticAI prompt queue, triggering immediate re-evaluation.
4. **Integration Test:** Run a simulated scenario where the TurtleBot3 encounters an unexpected obstacle during navigation. Verify the interrupt fires, the LLM re-plans, and the robot recovers — all without manual intervention.

**Exit Criteria:** The orchestrator maintains a live state cache from ROS2 telemetry, the LLM can query discrete state summaries on demand, and critical anomalies trigger automatic re-evaluation of the current plan.

---

## **Phase 2: Hardware Migration (TurtleBot3 / RPi4)**

**Objective:** Transition the Phase 1 software stack to control a physical TurtleBot3 (Raspberry Pi 4) running ROS2 Humble over a local Wi-Fi network.

**Transport Change:** Switch the MCP adapter from `rosbridge` to `local` transport (rclnodejs). Both the base station and robot run ROS2 Humble with CycloneDDS — direct DDS communication eliminates the rosbridge overhead. Single config change in `config/agenticros.json`:

```json
{ "transport": { "mode": "local" }, "local": { "domainId": 184 } }
```

**Milestones:**

1. **CycloneDDS Network Tuning:** Validate DDS multicast between the base station and RPi4 on the same subnet. Already partially configured with `cyclonedds.xml` peer config `192.168.0.25`. Confirm stable topic discovery without rosbridge.
2. **rclnodejs Build:** Install and compile `rclnodejs` inside the Orchestrator container against ROS2 Humble. Verify the MCP adapter can connect in `local` mode and discover topics directly via DDS.
3. **Safety Grounding:** Validate hardware-level interrupts (E-stops, bumper sensors). Ensure the rclpy Aggregation Layer intercepts safety events and forces LLM context updates. Implement velocity clamping via the MCP adapter's safety config.
4. **Physical Nav2 Tuning:** Calibrate Nav2 parameters for real-world odometry drift and physical environment mapping. Test SLAM Toolbox integration for dynamic map building.

**Exit Criteria:** The physical TurtleBot3 navigates a room, avoids obstacles, and responds to natural language commands with equivalent reliability to Phase 1 simulation. Transport runs over direct DDS with no rosbridge overhead.

---

## **Phase 3: Edge AI & High-Frequency Inference**

**Objective:** Integrate heavy compute models for vision, language, and anomaly detection. Eliminate internet dependency.

**Milestones:**

1. **Local LLM Migration:** Transition from cloud APIs (Gemini/Groq) to local inference via Nvidia NIM containers or Ollama on the base station. PydanticAI's provider-agnostic design makes this a config-level change.
2. **Deep Learning Pipeline:** Deploy DeepStream/TensorRT containers as native ROS2 nodes for real-time object detection, pose estimation, and action recognition.
3. **Aggregation Layer Integration:** Connect the high-frequency inference output to the Phase 1B State Cache. Pipe detection results, skeletal data, and audio classifications through the existing interrupt system.
4. **Complex Agentic Tasks:** Test end-to-end tool chaining workflows requiring vision + navigation + reasoning (e.g., "Find the red cup, track it, and tell me if it falls off the table").

**Exit Criteria:** A fully autonomous, internet-independent robotic system capable of real-time semantic reasoning, high-frequency visual processing, and complex multi-tool agentic workflows.