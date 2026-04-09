## **SKILL_ID: emergency_escalation DESCRIPTION: Protocols for handling physical anomalies or critical failures.**

# **Skill: Emergency Escalation & Triage Protocol**

If an anomaly is detected (e.g., via `ros2_subscribe_once` on a diagnostic topic), you must immediately triage.

## **1. Visual Verification & Chaining**

Do not trigger alarms on sensor noise. You MUST achieve visual verification.
* **Orient:** Use `ros2_publish` to `/cmd_vel` or `ros2_cmd_vel_duration` to turn towards the anomaly.
* **Chain Vision:** 
    1. Call `ros2_camera_snapshot` for the human timeline.
    2. IMMEDIATELY call `ros2_vla_query` with a severe prompt (e.g., "Is there a person on the floor? Are they injured?").

## **2. Immediate Kinetic Mitigation**

If verified:
* **Halt:** Issue a zero-velocity command using `ros2_publish` to `/cmd_vel`.
* **Safe State:** Stop all active navigation goals via the relevant action client if necessary.

## **3. Communication**

1. Report the VLA reasoning result to the user immediately.
2. Provide the snapshot timestamp so the user can review the frame.
3. Keep the robot stationary until "all clear".