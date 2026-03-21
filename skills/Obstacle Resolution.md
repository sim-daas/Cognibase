## **SKILL\_ID: obstacle\_resolution DESCRIPTION: Decision matrix for handling blocked paths, including when to detour, wait, or physically interact with an obstacle.**

# **Skill: Obstacle Resolution Matrix**

When check\_action\_status returns ABORTED due to a blocked path, do not blindly loop the navigation command. Evaluate the obstacle and resolve it.

## **1\. Classification**

Use capture\_camera\_frame and query\_vla\_pipeline. Ask the VLA to classify the blocking entity into one of three categories:

* **A: Dynamic Actor** (Human, Forklift, Pet)  
* **B: Lightweight Debris** (Empty cardboard box, loose paper)  
* **C: Hard/Impassable Object** (Pallet, closed door, heavy equipment)

## **2\. Resolution Execution**

* **If A (Dynamic):** Humans and vehicles move. Use ask\_human\_clarification (TTS) to say "Excuse me, please clear the path." Wait 10 seconds. Re-evaluate.  
* **If B (Lightweight):** If the item poses zero risk to the drivetrain, publish a localized velocity override to push through it. *(Note: rely on deterministic ROS nodes for pushing, do not attempt to micro-manage /cmd\_vel via the LLM).*  
* **If C (Hard/Impassable):** Do not interact. Query query\_semantic\_memory for an alternate route. If no alternate route exists, use send\_notification to request human intervention.