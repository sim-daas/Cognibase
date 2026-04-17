# AgenticROS Skills System

In the current architecture, **Skills** are not binary packages or code plugins. They are **high-level behavioral context documents** written in Markdown that guide the Agentic Reasoning Engine when performing specialized tasks.

## 1. Skill Storage & Structure

Skills are stored as `.md` files in the `/home/ubuntu/githubrepos/Cognibase/skills/` directory. Each skill file must follow this structure:

```markdown
---
name: "Skill Name"
description: "A short one-sentence summary of what this skill does."
---
# Detailed Instructions
- Step 1: Execute tool X
- Step 2: Interpret result Y
- Step 3: Handle error Z
...
```

The YAML front-matter (`--- ... ---`) is used by the system to "index" the skill without loading the full text immediately, saving tokens in the system prompt.

## 2. The Two-Stage Loading Process

To maintain efficiency while allowing for dozens of complex skills, CogniBot uses a **Late-Binding** approach:

### Stage 1: The Skill Index (Discovery)
At startup, `cognibot/skill_loader.py` scans the skills directory. It extracts ONLY the `name` and `description` from the YAML header. 
This index is appended to the **Available Skills** section of the agent's static system prompt (`SOUL.md`).

The agent "knows" what it can do, but it doesn't yet have the detailed procedure.

### Stage 2: Context Injection (Execution)
When the agent receives a task that matches a skill description, it is instructed by `SOUL.md` to call:

`load_skill_context(skill_id="SKILL_NAME")`

This native Python tool reads the **entire Markdown file** and injects it into the agent's current conversation context. The agent then follows the specific instructions inside that document to complete the mission.

## 3. Creating a New Skill

To add a new capability to your robot:

1. Create a new `.md` file in the `skills/` folder.
2. Define a clear `name` and `description` in the header.
3. Write precise, tool-centric instructions using standard Markdown.
4. Restart the `cognibot` agent. The new skill will automatically appear in its "Available Skills" index.

## 4. Why this system?

- **Zero-Code Extensions**: You can give the robot new behaviors by writing instructions, not Python code.
- **Token Efficiency**: The agent only "reads" the manual for a specific task when it's actually doing it, keeping the primary prompt lightweight.
- **Dynamic Updates**: Modifying a Markdown file in `skills/` immediately updates the robot's logic for the next time it loads that context.

---

## Technical Reference

- **Loader Implementation**: `cognibot/skill_loader.py`
- **Agent Integration**: `cognibot/agent.py`
- **Tool Definition**: `load_skill_context`
- **Registry**: The file basename (e.g., `navigation`) is the `skill_id`.
