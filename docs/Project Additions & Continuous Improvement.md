# **CogniBot – Project Additions & Continuous Skill Improvement**

## **1. Introduction**
CogniBot is an agentic robotics platform that couples a PydanticAI orchestrator with a lightweight MCP bridge and ROS 2‑based hardware control. The core pipeline already supports natural‑language instruction, dynamic skill injection, and deterministic Nav2 navigation. The following sections outline the planned extensions, the automated skill‑review workflow, and how semantic memory will be leveraged to make navigation “smarter” than the out‑of‑box Nav2 behavior.

---

## **2. Project Additions**

| Component | What is added | Why it matters | Key source |
|-----------|---------------|----------------|------------|
| **Dynamic Tool Registry** | An automatic discovery module that scans the `skills/` directory for `.md` files, extracts the `DESCRIPTION` header, and populates a runtime “skill index”. | Keeps the system prompt concise while allowing the LLM to load full skill text on demand (`load_skill_context`). | [8] |
| **Skill‑Review Engine** | After every mission, the orchestrator runs a post‑mission log parser that: <br>1) extracts the sequence of tool calls. <br>2) Cross‑checks against expected outcomes (e.g., navigation goal reached). <br>3) Generates a structured JSON review that highlights failures, latencies, and suggested rule‑changes. | Provides an audit trail and a basis for automatic skill refinement. | [8] |
| **Incremental Skill Update API** | A REST endpoint (`/skills/update`) that accepts a patched skill file. The orchestrator reloads the skill without restarting, updates the skill index, and re‑injects the new description into the LLM prompt. | Enables zero‑downtime deployment of bug‑fixes or new heuristics. | [8] |
| **Memory‑Backed Navigation Planner** | A wrapper around Nav2 that reads a pre‑computed “preferred‑route” from semantic memory (`query_semantic_memory`) and pushes it to Nav2 via the `set_plan` service before falling back to standard planning. | Allows the agent to *bias* the planner toward user‑preferred paths, saving time and reducing collisions. | [4], [10] |
| **Context‑Aware Safety Layer** | A lightweight watchdog that monitors safety‑related topics (`/battery_state`, `/temperature`, `/human_pose`) and can override Nav2 goals if thresholds are breached. | Adds an extra safety net that can autonomously pause or cancel navigation. | [5] |
| **Telemetry Aggregator** | A background thread that streams all relevant ROS 2 topics to a lightweight in‑memory time‑series DB. The DB is queried by skills like `obstacle_resolution` to decide whether a dynamic actor has moved. | Gives higher‑level skills up‑to‑date situational awareness without constant topic subscription. | [3] |

---

## **3. Auto Skill Update / Review**

1. **Execution Logging** – Each tool call is logged with a timestamp, input, and output.
2. **Outcome Verification** – For navigation skills, the engine checks whether the goal pose was reached within a tolerance; for sensor‑based skills, it verifies that the returned value meets expectations.
3. **Automated Report Generation** – The review JSON contains:
   * `success_rate` per skill,
   * `average_latency`,
   * `failed_calls` with error codes,
   * `suggested_thresholds` for any param‑tuning.
4. **Developer Dashboard** – The JSON is posted to a web UI (React/Flask) where operators can drill down, approve changes, or trigger a live update via the `/skills/update` API.

This loop turns real‑world experience into a living knowledge base, allowing the agent to adapt without manual code changes.

---

## **4. Semantic Memory – Definition & Role**

| Domain | What is stored | Why it is useful |
|--------|----------------|------------------|
| **Spatial Knowledge** | Waypoints, known obstacles, alternate routes, building layouts. | Enables the agent to *plan* ahead of Nav2, reducing goal‑retries. |
| **Behavioral History** | Past human interactions, successful/failed commands, operator preferences. | Helps the agent anticipate user intent and adjust its responses accordingly. |
| **Environmental Context** | Time‑of‑day lighting conditions, typical crowd densities, scheduled maintenance windows. | Allows context‑aware decision making (e.g., avoid busy corridors at peak). |
| **Policy & Strategy** | Custom rules like “never drive near wet floor” or “prioritize charging before a long task”. | Gives the agent higher‑level control beyond Nav2’s low‑level planner. |

Semantic memory is queried by skills via the `query_semantic_memory` tool and updated using `load_skill_context` (for new rules) or explicit `query_semantic_memory` updates in the skill code. Because the memory is *semantic* rather than raw sensor data, it can be used by the LLM to reason about past events and plan future actions.

---

## **5. Smarter Navigation Using Semantic Memory**

Nav2 itself is a deterministic planner that takes a pose goal and a costmap. By augmenting Nav2 with semantic memory, the agent can influence the planner in several ways:

| Technique | How it works | Tool(s) involved |
|-----------|--------------|-----------------|
| **Pre‑planned Route Injection** | Before calling `/navigate_to_pose`, the agent queries `query_semantic_memory` for a list of waypoints that represent the *preferred* path. It then uses the Nav2 `set_plan` service to hand the planner a pre‑computed trajectory. | `query_semantic_memory`, `ros2_service_call` (SetPlan) |
| **Dynamic Costmap Modification** | When semantic memory indicates a *temporary* obstacle (e.g., “person moving through hallway”), the agent publishes an obstacle marker to the global or local costmap (`ros2_publish`). Nav2 immediately re‑plans around it. | `ros2_publish` |
| **Parameter Tuning** | Based on past performance (e.g., frequent goal failures in a corridor), the agent can adjust planner parameters such as `planner_frequency` or `recovery_behavior_names` via `ros2_param_set`. | `ros2_param_set` |
| **Behavior‑Tree Selection** | Nav2 supports multiple BTs. The agent can choose the BT that best matches the current context (e.g., a “slow‑safe” BT when a child is nearby). | `ros2_action_goal` with `goal.behavior_tree` field |

Because semantic memory stores *why* a particular path was chosen (e.g., “the corridor was crowded on weekday mornings”), the agent can *re‑evaluate* that decision in real time, leading to faster, safer, and more human‑aligned navigation.

---

## **6. Conclusion**

The outlined additions create a feedback loop:
1. **Sensors → Skills → Tools → Actions** generate real‑world data.
2. **Automated reviews** surface performance metrics.
3. **Semantic memory** records context, rules, and policy.
4. **Nav2 is guided** by memory‑driven hints, cost‑map tweaks, and BT selection.

With these components in place, CogniBot moves from a deterministic navigation robot to an *agentic* system that learns from experience, adapts its skills on the fly, and navigates in a way that respects both physical constraints and human intent.
