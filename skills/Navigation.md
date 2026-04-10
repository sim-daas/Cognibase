## **SKILL_ID: navigation DESCRIPTION: Procedures for Nav2 coordinates, pose checking, and spatial movement.**

# **Skill: Navigation (Nav2 / SLAM)**

## **0. Memory-Biased Pre-Planning (ALWAYS DO FIRST)**

Before issuing any navigation goal to a named destination, call `plan_memory_route`:

```
plan_memory_route(destination_label="charging dock")
```

This queries all four memory domains and returns:
- Known waypoints with x/y/theta coordinates
- Previously observed obstacles or hazards on the route
- Behavioral history (e.g., past goal failures in this area)
- Active policies (e.g., "avoid wet floor near Room 204")

**Decision tree based on the returned plan:**

| Memory result | Action |
|---|---|
| Waypoints found with x/y/theta | Use `/navigate_through_poses` to inject the full preferred path |
| Hazard noted on direct path | Adjust target coordinates to avoid the hazard area |
| Policy violation detected | Halt, inform operator, request clearance |
| No memory found | Proceed with standard `/navigate_to_pose` below |

---

## **1. Checking Current Position (Localization)**

Before navigating, or if the user asks where the robot is, you must check its current pose. 

Use the `ros2_subscribe_once` tool on the localization topic:
- **Topic:** `/amcl_pose` (if Nav2 is fully localized on an existing map) or `/odom` (if relying strictly on odometry).
- **Type:** `geometry_msgs/msg/PoseWithCovarianceStamped` (for amcl_pose) or `nav_msgs/msg/Odometry` (for odom).

Extract the `pose.pose.position.x` and `pose.pose.position.y` values from the JSON response to understand the robot's real-world coordinates.

## **2. Sending a Navigation Goal (Nav2)**

To command the robot to autonomously drive to a specific spatial coordinate (x, y), you must use the `ros2_action_goal` tool to interface with Nav2's `NavigateToPose` action server.

- **Action Name:** `/navigate_to_pose`
- **Action Type:** `nav2_msgs/action/NavigateToPose`

**Goal JSON Structure:**
You must provide the exact payload format below in the `goal` parameter. Replace `[X_COORD]` and `[Y_COORD]` with the target floats.

```json
{
  "pose": {
    "header": {
      "frame_id": "map"
    },
    "pose": {
      "position": {
        "x": [X_COORD],
        "y": [Y_COORD],
        "z": 0.0
      },
      "orientation": {
        "x": 0.0,
        "y": 0.0,
        "z": 0.0,
        "w": 1.0
      }
    }
  },
  "behavior_tree": ""
}
```

### **Handling Orientation (Headings)**
If the user requests a specific facing direction (e.g., "face North", where theta = 1.57 radians), you must calculate the quaternion for the `orientation` field:
- `x` = 0.0
- `y` = 0.0
- `z` = `sin(theta / 2)`
- `w` = `cos(theta / 2)`
If no heading is specified, always default to `z: 0.0, w: 1.0`.

## **3. Execution Constraints**
- Always confirm that the coordinates are safe and within known boundaries.
- If the `ros2_action_goal` call fails, report the error to the user and explain that the navigation stack may not be running or the coordinate is unreachable.
- Never loop the navigation call blindly; if it fails, stop and request human clarification.

## **4. Post-Navigation Memory Update**

After a **successful** navigation goal, store the route for future use:

```
store_memory(
    domain="spatial",
    content="Successfully navigated to [destination] at x=[X], y=[Y]. Path was clear.",
    metadata={"label": "[destination]", "x": [X], "y": [Y], "theta": [THETA], "success": true}
)
```

After a **failed** navigation goal, record the failure reason:

```
store_memory(
    domain="behavioral",
    content="Navigation to [destination] failed: [error reason]. Attempted coordinates: x=[X], y=[Y].",
    metadata={"label": "[destination]", "success": false, "reason": "[error]"}
)
```

This builds a living spatial knowledge base that improves navigation accuracy over time.
