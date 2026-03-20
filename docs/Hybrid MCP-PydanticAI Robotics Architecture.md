# **Architecture Document: Hybrid MCP-PydanticAI Robotics System**

## **1\. Executive Summary**

This architecture defines a custom, agentic robotics control system enforcing a strict boundary between non-deterministic reasoning (the LLM) and deterministic execution (hardware).

By utilizing PydanticAI as the orchestrator and a Node.js MCP server as a strict translation bridge, we eliminate UI bloat and ensure rigorous data validation. The system relies entirely on native ROS 2 CycloneDDS for inter-process and inter-device communication on a shared subnet, operating within strictly defined Docker containers.

## **2\. Hardware, Network, and Container Topology**

The system operates on a Distributed Compute Model across a local subnet.

* **The Base Station (PC/Laptop/Edge Server):**  
  * *Container 1 (The Orchestrator):* Python environment running the PydanticAI Agent. Maintains state, handles the ReAct loop, and manages LLM API interactions.  
  * *Container 2 (The Bridge):* Node.js process running the AgenticROS MCP server. Communicates via stdio with Container 1 and joins the CycloneDDS network natively.  
  * *Container 3 (Local Inference \- Optional):* Nvidia NIM for local LLM execution, entirely isolated and accessed via REST/gRPC by Container 1\.  
* **The Robot (TurtleBot3 / Jetson Orin):**  
  * *Container 4 (Nav & Control):* Runs the ROS 2 DDS layer, Nav2 stack, and hardware controllers.  
  * *Container 5 (Deep Learning Pipeline):* Runs Nvidia DeepStream or custom inference models as native ROS 2 nodes, publishing high-frequency telemetry.

## **3\. Core Software Stack**

* **Layer 1: The Agent Orchestrator (PydanticAI / Python)**  
  * *Role:* Handles the ReAct loop, conversation memory, and strict output validation via Pydantic models.  
  * *Dynamic Context Manager:* A custom Python module that injects the SOUL.md and a synthesized "Skill Index" (1-2 line descriptions) into the initial system prompt. It exposes a native PydanticAI tool load\_skill\_context(skill\_id) that allows the LLM to pull the full text of a skill file into its working memory only when required.  
* **Layer 2: The Translation Bridge (AgenticROS MCP Server / Node.js)**  
  * *Role:* A dumb pipe exposing ROS 2 capabilities as JSON-RPC MCP tools. Transport is native CycloneDDS.  
* **Layer 3: The Hardware Interface (ROS 2 / CycloneDDS)**  
  * *Role:* C++/Python ROS 2 nodes executing binary DDS messages directly.

## **4\. Execution Pipeline: Asynchronous Actions (Nav2)**

1. **Prompt & Validation:** User requests navigation. PydanticAI validates the schema.  
2. **Dispatch:** PydanticAI calls send\_nav\_goal via stdio to the Node.js bridge.  
3. **Action Initiation:** The bridge publishes the native ROS 2 Action Goal over CycloneDDS.  
4. **Immediate Return:** The bridge immediately returns status: accepted to PydanticAI.  
5. **Status Polling:** The Python orchestrator uses check\_action\_status(goal\_id) to poll the robot asynchronously.  
6. **Resolution:** Once the status returns SUCCEEDED or ABORTED, the context is updated.

## **5\. High-Frequency Telemetry & Inference (Deep Learning)**

**RULE:** High-frequency data MUST NEVER be fed directly into the PydanticAI ReAct loop.

* **The Aggregation Layer:** A background Python thread subscribes to high-frequency CycloneDDS topics and caches the state.  
* **LLM Interaction:** The LLM uses MCP tools to query this discrete text summary.  
* **Event Triggers:** For critical anomalies, the Python background thread acts as an interrupt, injecting a forced observation into the LLM's prompt queue to trigger immediate re-evaluation.

## **6\. Dynamic Skill Injection (Context Management)**

PydanticAI does not support OpenClaw-style skill loading out of the box. This is solved via the following strict pipeline:

1. **Boot Initialization:** Python scans the /skills directory. It extracts the DESCRIPTION metadata block from every .md file.  
2. **System Prompt Construction:** The PydanticAI system prompt is statically compiled using SOUL.md \+ the extracted Skill Index.  
3. **On-Demand Loading:** If the LLM determines a task matches a skill description, it calls the internal Python tool load\_skill\_context(skill\_id). The text is appended to the message history, grounding the next step of the ReAct loop without bloating the permanent system prompt.

## **7\. Tooling Ecosystem**

1. **Navigation:** Maps\_to\_point, initiate\_auto\_docking, track\_object  
2. **Vision:** capture\_camera\_frame, get\_3d\_depth, detect\_objects\_coco, filter\_color\_hsv, query\_vla\_pipeline, read\_text\_ocr, scan\_qr\_code  
3. **State:** estimate\_pose, recognize\_action, read\_temperature, classify\_audio\_event  
4. **Interaction:** ask\_human\_clarification, send\_notification, trigger\_alarm, control\_appliance  
5. **Memory:** query\_semantic\_memory, load\_skill\_context

## **8\. Agentic Execution Patterns (Use Cases)**

The architecture supports dynamic tool chaining, entirely replacing the need for bespoke, hardcoded ROS behavior trees.

* **Dynamic Tool Chaining:** (e.g., "Count workers in high-vis yellow.") The agent navigates to the bay, loops camera frames, extracts person bounding boxes via COCO, and passes *only* those coordinates to the HSV color filter tool, autonomously counting matches.  
* **Contextual Escalation:** (e.g., "Keep an eye on Grandpa.") The agent locks onto a subject via VLA inference and background-runs Action Recognition. If a fall occurs, an interrupt is triggered, bypassing standard loops to immediately execute alarm and messaging tools.  
* **Semantic Verification:** (e.g., "Make sure the oven is off.") The agent routes to the kitchen, uses COCO to verify an empty room, and upon logical confirmation, fires the Appliance Control tool to cut smart-plug power.  
* **Complex Subject Isolation:** (e.g., "Follow the guy carrying the box.") Rather than relying on rigid UI click-to-track interfaces, the agent uses a VLA pipeline to ask for bounding boxes matching the semantic prompt, then feeds those exact coordinates to the deterministic Object Tracking tool.  
* **Human-in-the-Loop Disambiguation:** If ambiguity arises (e.g., three workers present when asked to "follow the worker"), the agent suspends the action goal and utilizes Text-to-Speech tools to physically request clarification before proceeding.