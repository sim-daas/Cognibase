## **SKILL_ID: visual_search DESCRIPTION: Heuristics for finding lost or ambiguously defined objects. Uses tool chaining and visual reasoning.**

# **Skill: Dynamic Visual Search Framework**

Do not guess where objects are. When instructed to find an item with no known coordinates, execute the following heuristic framework:

## **1. Contextual Prediction**

Use logical inference to identify potential locations. (e.g., A "toolkit" belongs in the garage; a "blue bottle" belongs in a kitchen).

## **2. Waypoint Exploration**

Publish sequential navigation goals using `ros2_action_goal`.
- **Action:** `/navigate_to_pose`
- **Rule of Halts:** Do not attempt to process vision while the base is moving. Wait for the action to succeed, then poll the sensors.

## **3. Tool Selection & Chaining (IMPORTANT)**

When you arrive at a waypoint, you MUST chain visual tools to "look" around:

1. **Snapshot (for User):** Call `ros2_camera_snapshot` so the human operator can see what you see.
2. **Visual Reasoning (for Agent):** IMMEDIATELY call `ros2_vla_query` with a prompt identifying the object (e.g., "Do you see a blue bottle on the table?"). 
3. **Verification:** If the VLA response is ambiguous, call `ros2_depth_distance` to check if an object is within physical reach.

## **4. Failure Protocol**

If an area is exhausted, move to the next logical waypoint. If all logical waypoints are exhausted, stop and report: "Search matrix exhausted. Item not detected in primary zones."