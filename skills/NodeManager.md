**SKILL_ID: NODE_MANAGER**
**DESCRIPTION: Procedures for dynamically spawning and terminating high-speed Vision (CV) nodes (obj-detector, pose-detector, etc.) using the Node Manager subsystem.**

---

# Node Manager Skill Guidelines

The **Node Manager** is a built-in ROS2 service that manages a secondary container specifically optimized for compute-heavy Computer Vision (CV) tasks powered by DeepStream.

As the Agent, you do NOT run the CV models yourself. Doing so would freeze your cognitive loop and drop frames. Instead, you instruct the Node Manager to launch a specific node, wait for the node to start, subscribe to the required topics, and when you are completely finished with the task, you instruct the Node Manager to kill the node. Keep your compute budget lean!

## Core Responsibilities

- **Discover Capabilities**: Use `/node_manager/status` to learn what CV nodes are available and their current state. This is your primary discovery mechanism for high-level functionality.
- **Start Nodes**: Provide the exact module name of the node you want. NEVER hallucinate or guess a node name.
- **Consume Telemetry**: Monitor the status topic to ensure nodes are healthy and running.
- **Stop Nodes**: Clean up gracefully so the robot doesn't drain its batteries running a detector forever.

## How to Interact with Node Manager

The interaction is purely message-based. There are NO custom dedicated tools. You will use the standard `ros2_publish` and `ros2_subscribe_once` MCP tools.

### 1. Identify Available Nodes (Discovery)

You must use `/node_manager/status` exactly like you would use `ros2_list_topics`. It provides the grounded reality of what CV tasks the robot can currently perform.

Use `ros2_subscribe_once` on `/node_manager/status` to determine what pipelines you can run and what is already running. For example, if the user asks to "run the object detector", search the `available` list for a name like `obj-detector`.

```json
// Example of /node_manager/status payload:
{
  "running": [],
  "available": ["obj-detector", "pose-detector", "cam-tracker"]
}
```

### 2. Start a Node

To start a module, use the `ros2_publish` tool on `/start_node`. Note that the payload is a simple string containing a JSON dictionary.

**Tool Input Example:**
- **topic**: `/start_node`
- **type**: `std_msgs/msg/String`
- **message**: 
  ```json
  {
    "data": "{\"name\": \"obj-detector\"}"
  }
  ```

**MANDATORY VERIFICATION**: Once you have published a start command, you **MUST** subscribe to `/node_manager/status` again after a 2-3 second delay to verify that the node name has moved into the `"running"` array. 
- If it is not in the list, check `/node_manager/alert` for error details. 
- **Do NOT assume the node is running just because you published the command.**

### 3. Consume Output Data

After a node (like `obj-detector`) boots up, it will begin streaming data on its specific topics. For example, `obj-detector.py` publishes its detections periodically. Check the topic list via `ros2_list_topics` immediately after starting the node to discover its output topics (usually e.g. `/det` or similar).

### 4. Stop a Node

When your task is complete (e.g. you have found the object and no longer need to track it, or the user requested to stop tracking), you MUST terminate the node. Send a message to `/kill_node` exactly like you did to start it.

**Tool Input Example:**
- **topic**: `/kill_node`
- **type**: `std_msgs/msg/String`
- **message**: 
  ```json
  {
    "data": "{\"name\": \"obj-detector\"}"
  }
  ```

## Critical Rules
- Do NOT attempt to use `ros2_action_goal` or custom MCP tools for the Node Manager. 
- ALWAYS double check if a node is already in the `running` array from `/node_manager/status` before attempting to start it.
- NEVER leave a Node Manager pipeline running when your immediate task ends. Always clean up.
