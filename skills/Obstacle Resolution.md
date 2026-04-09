## **SKILL_ID: obstacle_resolution DESCRIPTION: Decision matrix for handling blocked paths using visual reasoning.**

# **Skill: Obstacle Resolution Matrix**

When a navigation action (to `/navigate_to_pose`) fails or a path is blocked, do not blindly loop. Evaluate the obstacle and resolve it.

## **1. Classification & Chaining**

You must characterize the obstacle before deciding. Chain these tools:
1. **`ros2_camera_snapshot`**: Provide visual context to the user.
2. **`ros2_vla_query`**: Prompt: "What is blocking the path? Classify as: [A: Human/Moving, B: Small/Pushable, C: Static/Solid]".

## **2. Resolution Execution**

* **If A (Moving Actor):** Use `ros2_publish` to a TTS topic (if available) or simply wait and retry `ros2_action_goal` after 10 seconds.
* **If B (Pushable):** If safe, you may use `ros2_cmd_vel_duration` to gently nudge or clear the path. **Safety First:** Do not push if it looks fragile.
* **If C (Static):** Do not interact. Request a New Path or notify the human operator.