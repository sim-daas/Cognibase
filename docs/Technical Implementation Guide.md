# **Technical Implementation Guide: Hybrid MCP-PydanticAI System**

This document defines the exact software components and integration points required to build the system.

## **1\. System Topology & Networking (Strict Requirements)**

* **Base Station (Host):** Runs Docker Compose containing the Orchestrator (Python) and Bridge (Node.js).  
* **Robot/Simulation:** Runs native ROS 2 packages.  
* **Interconnect:** CycloneDDS.  
* **Mandate:** All Docker containers handling ROS 2 traffic MUST use network\_mode: "host". Default bridge networks block CycloneDDS UDP multicast discovery.

## **2\. Layer 2: The Translation Bridge (Node.js / agenticros)**

You will leverage the existing agenticros/agenticros repository to serve as your MCP server. It acts as a stateless translator between JSON-RPC and ROS 2 DDS.

### **Modifications Required to agenticros:**

1. **Transport Configuration:** Configure the core to use local ROS 2 native bindings (via rclnodejs or similar) configured for CycloneDDS, completely disabling WebSockets/rosbridge.  
2. **Async Nav2 Tool Overhaul:** \* Modify the existing send\_nav\_goal tool. It must NOT await the action server's final result. It must publish the goal, generate a UUID, and immediately return { "status": "accepted", "goal\_id": "\<UUID\>" }.  
   * Create a new tool check\_action\_status. It accepts a goal\_id and queries the internal ROS 2 action client cache, returning EXECUTING, SUCCEEDED, or ABORTED.

## **3\. Layer 1: The Orchestrator (Python / PydanticAI)**

This is a completely custom Python application you must build. It acts as the brain, connecting the LLM to the Node.js MCP server.

### **Component A: MCP Client Module**

* **Interface:** Utilize the mcp.client.stdio library.  
* **Function:** Spawns the agenticros Node.js process as a subprocess. Captures its stdout and stdin to facilitate JSON-RPC tool discovery and execution.

### **Component B: Dynamic Context Manager (Skill Loader)**

* **Boot Scraper Module:** A startup script that recursively iterates through the /skills directory. It uses regex or a YAML parser to extract the DESCRIPTION block from every .md file.  
* **Index Generator:** Compiles these descriptions into a single string array.  
* **System Prompt Compiler:** Concatenates SOUL.md and the Index Generator output. This forms the static, immutable system prompt for PydanticAI.  
* **load\_skill\_context Tool:** A native Python PydanticAI @tool. It accepts a skill\_id, reads the corresponding .md file from the disk, and returns the raw string content to the LLM.

### **Component C: High-Frequency Aggregation Layer**

* **Background Thread:** A native Python rclpy thread running completely outside the PydanticAI ReAct loop.  
* **State Cache:** Subscribes to high-frequency ROS 2 topics (e.g., /tf, /odom, /object\_detections). It continuously overwrites a thread-safe dictionary with the latest values.  
* **query\_state Tool:** A native PydanticAI @tool that simply reads from the State Cache and returns a formatted JSON string to the LLM.

### **Component D: The PydanticAI Agent**

* **Initialization:** Loads the System Prompt, registers the native Python tools (load\_skill\_context, query\_state), and dynamically registers the MCP tools discovered from Component A.  
* **ReAct Loop:** Handles user input, invokes tools via stdio to the Bridge or internally, and manages prompt truncation to prevent token exhaustion.