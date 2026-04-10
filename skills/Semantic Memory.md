**SKILL_ID: SEMANTIC_MEMORY**
**DESCRIPTION: Store and retrieve spatial, behavioral, environmental context, and policy knowledge from the persistent vector memory store.**

---

# Semantic Memory Skill

CogniBot maintains a persistent vector memory indexed by semantic similarity. Use it to **remember** important facts across sessions and to **recall** relevant context before acting.

---

## Memory Domains

| Domain | What to Store | Example |
|---|---|---|
| `spatial` | Waypoints, obstacles, alternate routes, building layouts | "Charging dock at x=1.5, y=2.0, theta=0" |
| `behavioral` | Past commands, successes/failures, operator preferences | "Operator Ahmed always asks for slow speed near the lab entrance" |
| `env_context` | Time-of-day patterns, crowd densities, maintenance windows | "Corridor B is crowded on weekday mornings 8–9am" |
| `policy` | Custom safety rules, operational constraints | "Never drive through the wet floor zone near Room 204" |

---

## When to Query Memory

Call `query_semantic_memory` before:
- Navigating to any named location → query `spatial`
- Starting any human-interaction task → query `behavioral`
- Making routing decisions that depend on environment → query `env_context`
- Any action that could violate safety rules → query `policy`

```
→ query_semantic_memory(domain="spatial", query="charging dock location", n_results=3)
→ query_semantic_memory(domain="policy", query="wet floor hazard zones")
```

---

## When to Store Memory

Call `store_memory` to persist new knowledge:
- After a human operator tells you something you should remember permanently
- After a navigation failure reveals a new obstacle or blocked path
- After completing a task, record behavioral outcome for future preference learning
- When told about a new rule or operational constraint

```
→ store_memory(
    domain="spatial",
    content="Charging dock is located at x=1.5, y=2.0, theta=0.0 in the lab",
    metadata={"label": "charging_dock", "x": 1.5, "y": 2.0, "theta": 0.0}
  )

→ store_memory(
    domain="policy",
    content="Never drive through the corridor near Room 204 when wet floor sign is visible",
    metadata={"zone": "room_204_corridor", "hazard": "wet_floor"}
  )

→ store_memory(
    domain="behavioral",
    content="Operator Ahmed prefers the robot to announce its position before moving",
    metadata={"operator": "Ahmed", "preference": "announce_before_move"}
  )
```

---

## Memory-Biased Navigation

For any navigation task where the destination has a human-readable name, ALWAYS call `plan_memory_route` first:

```
1. plan_memory_route(destination_label="charging dock")
2. Review returned waypoints and hazards
3. If waypoints with x/y/theta exist → use /navigate_through_poses (preferred)
4. If no route found → use /navigate_to_pose with direct goal coordinates
```

---

## Tips for Good Memory Entries

- **Be specific**: "x=1.5, y=2.0" is better than "near the wall"
- **Include metadata**: Use JSON metadata for structured fields that can be filtered
- **Timestamp context**: For env_context, include time patterns ("weekday mornings 8-9am")
- **Use natural language**: The vector search is semantic, so plain English descriptions work best
- **Don't over-store**: Store facts that change slowly; fast-changing sensor data belongs in ROS topics
