# CogniBot Demo Use Cases — TurtleBot3 Burger

> Target: YouTube demo video + college course presentation.
> Current system phase: TurtleBot3 Burger · ROS 2 Humble · rosbridge transport ·
> VLA (NVIDIA NIM) · Semantic Memory (LanceDB) · NodeManager · Nav2.

These four demos are ordered from simplest to most impressive. Each one exercises
a distinct capability pillar and can be filmed in 2–5 minutes.

---

## Demo 1 — "Ask the Robot What It Sees" (VLA Visual Reasoning)

**Core capability showcased:** `ros2_vla_query` + `ros2_camera_snapshot`

**The pitch (say this on camera):**
> "I'm going to type in plain English, and the robot will look around and tell me
> what it sees — no code, no ROS commands."

### Script

1. Place a colourful object (red cup, yellow sticky note, toy) in front of the robot.
2. In the TUI, type: **"What do you see in front of you right now?"**
3. Agent auto-chains:
   - `ros2_list_topics` (discovers camera)
   - `ros2_camera_snapshot` (shows frame in TUI via `feh`)
   - `ros2_vla_query` (sends frame to NVIDIA NIM → returns description)
4. Follow up: **"Is the path ahead clear enough for me to drive forward?"**
5. Agent answers with a safety verdict from the VLM.

### What makes it impressive
- The operator's terminal shows the tool call waterfall in real time (yellow panels).
- The camera image pops up automatically via `feh`.
- No config changes — works out of the box if `NVIDIA_API_KEY` is set.

### Setup checklist
- [ ] `NVIDIA_API_KEY` set in `config/cognibot.env`
- [ ] Camera topic publishing (`/camera/image_raw/compressed`)
- [ ] Object placed within camera FOV

---

## Demo 2 — "Navigate, Remember, Return" (Semantic Memory + Nav2)

**Core capability showcased:** `store_memory` · `plan_memory_route` · `ros2_action_goal`

**The pitch:**
> "Watch the robot learn the layout of the room over two runs. On the
> second run, it already knows where to go — no re-configuration."

### Script — Run 1 (teaching phase)

1. **"Go to the door at the end of the corridor."**
   - Agent: `plan_memory_route` → no memories yet → falls back to direct Nav2.
   - Nav2 navigates to manually typed coordinates.
   - After arrival, agent: **"Store this location as 'corridor_door'."**
   - `store_memory("spatial", "corridor_door at x=3.2, y=0.8, theta=0", {"label":"corridor_door"})`

2. **"Go back to the start."**
   - Navigate back; store as `"home_base"`.

### Script — Run 2 (memory-recall phase)

3. Restart the TUI (memory persists in LanceDB).
4. **"Go to the corridor door."**
   - Agent: `plan_memory_route("corridor_door")` → retrieves `x=3.2, y=0.8`
   - Uses `/navigate_to_pose` with recalled coordinates.
   - No human intervention needed.

### What makes it impressive
- Show the LanceDB memory file persisting on disk between runs.
- Point out the `plan_memory_route` output in the terminal — it shows *why* the
  robot chose those coordinates.
- Highlight: **the robot learned from one session and applied it to the next.**

### Setup checklist
- [ ] Nav2 running and localised (AMCL or SLAM Toolbox)
- [ ] `OLLAMA_URL` reachable with `nomic-embed-text` pulled
- [ ] A clear hallway / room for repeatable navigation

---

## Demo 3 — "Dynamic CV Pipeline On-Demand" (Node Manager)

**Core capability showcased:** NodeManager · `ros2_subscribe_once /node_manager/status`

**The pitch:**
> "The robot starts with only its basic sensors. I can ask it to activate
> a computer vision pipeline on the fly using plain language — and shut it down
> when I'm done, saving battery."

### Script

1. Ask: **"What CV capabilities do you have right now?"**
   - Agent calls `ros2_list_topics` + subscribes to `/node_manager/status`.
   - Shows: `{"running": [], "available": ["yolo-detector", "aruco-tracker"]}`

2. **"Start the YOLO object detector."**
   - Agent publishes `{"name": "yolo-detector"}` on `/start_node`.
   - NodeManager launches `yolo-detector.py` as a subprocess.
   - `/node_manager/status` updates: `{"running": ["yolo-detector"], ...}`

3. **"What objects can you see with the detector running?"**
   - Agent subscribes to the detector's output topic (e.g. `/detections`).
   - Returns structured detections: `[{class:"person", conf:0.92}, ...]`

4. **"Stop the detector to save battery."**
   - Agent publishes on `/kill_node`.
   - Status reverts to `{"running": [], ...}`

### What makes it impressive
- Live terminal shows the status topic updating in real time.
- Concept of **elastic compute on a robot** — spin up / tear down perception only
  when needed.
- Works without any ROS 2 launch file restarts.

### Setup checklist
- [ ] At least one pipeline script in `$PIPELINES_DIR` (e.g. a dummy that publishes on `/detections`)
- [ ] NodeManager running (`ros2 run cognibot node_manager`)
- [ ] `/node_manager/status` visible in `ros2 topic list`

> **Note:** If you don't have a real YOLO script ready, use a simple Python script
> that publishes dummy JSON detections — the NodeManager demo is about the
> *lifecycle orchestration*, not the ML model.

---

## Demo 4 — "Autonomous Environment Scout" (Full Pipeline)

**Core capability showcased:** All layers working together end-to-end.

**The pitch:**
> "I'm going to give the robot a single high-level instruction.
> It will plan its own route using memory, navigate, inspect each location
> visually with AI, store what it learned, and report back — autonomously."

### Script

1. Arrange 3 labelled locations in the room (a printed sign works: "Station A",
   "Station B", "Station C").

2. Type: **"Scout all three stations. At each one, take a visual inspection,
   describe what you see, check if there are any hazards or people, and
   remember the location for future missions."**

3. The agent autonomously chains:
   ```
   plan_memory_route("Station A") → coordinates if known, else asks user once
   ros2_action_goal("/navigate_to_pose", {Station A coords})
   ros2_query_state()           → check it arrived correctly via odometry
   ros2_vla_query("Describe this station. Any hazards or people?")
   store_memory("spatial", "Station A at x=...", {label:"station_a"})
   store_memory("behavioral", "Station A inspection: clear, no hazards")

   [repeat for B and C]

   Final report to operator
   ```

4. After the run, show the LanceDB tables — all three locations and their
   inspection notes are persisted.

5. **Bonus:** Ask it to go back to the first hazard-free station. It uses
   `plan_memory_route` without re-scanning.

### What makes it impressive
- Demonstrates the **full autonomy loop**: plan → move → perceive → remember.
- No operator involvement between stations — the robot is fully autonomous.
- Shows the **accumulation of knowledge** over a mission, not just reactive control.
- Great for a course because it touches every lecture topic:
  Navigation, Perception, Memory, Agentic Reasoning, Safety.

### Setup checklist
- [ ] Nav2 fully operational (SLAM map or known coordinates)
- [ ] Camera publishing + NVIDIA_API_KEY set
- [ ] Semantic memory initialised (Ollama + LanceDB)
- [ ] Enough open floor space for 3 waypoints (≥ 3 m apart)
- [ ] Printed station signs for visual clarity on camera

---

# Expert Level — Cognitive Reasoning & Tool Chaining

These demos showcase the "AGI" limits of the system, where the agent makes complex decisions based on policy, adapts to failures, and learns from human history.

## Demo 5 — the "Suspicious Package" Protocol

**Pillar:** Policy Enforcement + Safety Reasoning.

**The pitch:**
> "The robot isn't just a camera on wheels; it's a security guard. It knows the
> rules of the facility. If it finds something out of place, it uses its own
> spatial policy memory to decide what to do."

### Script
1. Define a "Secure Zone" in memory:
   - `store_memory("policy", "Secure Zone Policy: No bags or unknown items allowed in the main lobby after 6 PM.")`
2. Place a black backpack in the "lobby" area.
3. Command: **"Scout the lobby for any security violations."**
4. The Agent chains:
   - `ros2_vla_query` → "I see a black backpack near the entrance."
   - `query_semantic_memory("policy", "Is a bag allowed in the lobby right now?")`
   - Reasoning: "Policy says no bags after 6 PM. Current time is 8 PM."
   - Action: `ros2_publish("/node_manager/alert", {"msg": "SECURITY ALERT: Unauthorized item in lobby"})`
   - Action: `ros2_cmd_vel_duration` (backing away safely).

---

## Demo 6 — Dynamic Obstacle Negotiation & Map Update

**Pillar:** Failure Recovery + Memory Adaptation.

**The pitch:**
> "Standard robots just stop when they hit a chair. Our robot uses its vision
> to determine if the obstacle is temporary or permanent, and then updates
> its own brain so it doesn't make the same mistake twice."

### Script
1. Place a chair in the middle of a doorway.
2. Command: **"Go to the office."**
3. The Agent starts navigation → `ros2_query_state` flags a 0.1m obstacle in sector 'Front'.
4. Agent stops and calls: `ros2_vla_query("What is blocking the path? Is it a permanent wall or a movable object like a chair?")`
5. VLA returns: "It is a wooden chair."
6. Agent logic: "I will update my environmental context."
   - `store_memory("env_context", "Doorway blocked by a chair. Expect delays.")`
   - `plan_memory_route("office")` → Reasoning: "Doorway is blocked, finding alternate path via Hallway B."
7. Robot takes the long way around autonomously.

---

## Demo 7 — Context-Aware Retrieval (Behavioral Memory)

**Pillar:** Implicit Intent + Personality.

**The pitch:**
> "I can give the robot a vague command, and it will use its memory of our past
> interactions to figure out exactly what I want and where to get it."

### Script
1. Establish a history:
   - In a previous turn: "Always remember, for our Monday meetings, I need my coffee cup from the desk and the tablet from the shelf."
   - `store_memory("behavioral", "Monday meeting preferences: Cup @ Desk, Tablet @ Shelf")`
2. Command (on a Monday): **"I'm ready for the meeting, help me get set up."**
3. The Agent chains:
   - `query_semantic_memory("behavioral", "meeting setup")`
   - Reasoning: "Today is Monday. User needs Cup and Tablet."
   - Multi-point Nav: Move to Desk → `ros2_vla_query` ("Is the cup here?") → Move to Shelf → `ros2_vla_query` ("Got the tablet").
   - Action: `ros2_action_goal` (Return to user).

---

## Demo 8 — Autonomous "Knowledge Graph" Construction

**Pillar:** Systematic Exploration + Structured Reporting.

**The pitch:**
> "I can drop the robot in a new room and it will build a complete, structured
> inventory of every landmark and object, stored in a format my other systems
> can read."

### Script
1. Command: **"Enter the lab and build a full inventory of every object you see."**
2. The Agent enters and performs a systematic scan:
   - **Loop (8 times):**
     - `ros2_cmd_vel_duration` (rotate 45 degrees).
     - `ros2_vla_query` ("Identify every landmark and item in this frame.")
     - `ros2_depth_distance` (get exact distance to items for spatial mapping).
     - `store_memory` (save item, label, and coordinate).
3. Final Output: **"Inventory Complete. Detected 3 workstations, 1 3D printer, and 5 safety kits. Knowledge graph updated in spatial memory."**

---

## Filming Tips for Advanced Demos

| Tip | Detail |
|-----|--------|
| **Vertical Split Screen** | Show the **Thinking Output** (pydantic-ai logs) alongside the robot. Seeing the agent "reason" about the policy is the highlight of Demo 5. |
| **Prove Persistence** | For Demo 7, show that you *already deleted* the instructions from the chat history, yet the robot remembers them from the vector DB. |
| **Clock Check** | For Demo 5, show a physical clock or your computer clock to prove the "After 6 PM" policy logic is real. |
| **Tool Count** | Mention how many tools were chained. E.g., "The robot just executed 12 tool calls autonomously to fulfill that one sentence." |

---

## Filming Tips

| Tip | Detail |
|-----|--------|
| **Split screen** | Show TUI + physical robot simultaneously (phone on tripod) |
| **Slow the robot** | Set `normal` speed (0.12 m/s) — visually cleaner; use `ros2_param_set` live |
| **Highlight tool waterfall** | Zoom into the yellow tool-call panels in the TUI — that's the "magic" visible to viewers |
| **Voice-over the intent** | Describe *what the agent is deciding* while it runs — bridges the gap for non-ROS viewers |
| **Show memory persistence** | Between Demo 2 runs, `ls -la memory_db/` on camera to prove the database exists on disk |
