# **Project Roadmap: AgenticROS Implementation**

## **Phase 1: Simulation & Base Architecture**

**Objective:** Validate the software pipeline, tool execution, and dynamic skill loading in a zero-risk environment using the TurtleBot3 Gazebo simulation. No physical hardware or local deep learning models.

**Milestones:**

1. **Containerization:** Stand up the Base Station Docker Compose file (Python Orchestrator \+ Node.js Bridge). Establish DDS discovery with the isolated Gazebo Docker container.  
2. **Bridge Validation:** Successfully map basic Nav2 and Camera commands through the MCP Node.js bridge to the simulated robot.  
3. **Python Orchestrator Build:** Implement the PydanticAI ReAct loop and stdio MCP client.  
4. **Skill Pipeline Test:** Verify the Boot Scraper correctly injects tool descriptions into the system prompt and that the LLM successfully pulls full skill documents on demand.  
5. **Async Polling Test:** Issue a long-distance navigation command in Gazebo. Prove the LLM can query check\_action\_status while executing other contextual reasoning tasks simultaneously.

**Exit Criteria:** The LLM can autonomously navigate the simulated environment, "detect" mock objects (via simulated topic publishing), and dynamically load skills without crashing or blocking.

## **Phase 2: Hardware Migration**

**Objective:** Transition the Phase 1 software stack to control a physical TurtleBot3 (Raspberry Pi 4\) operating over a physical network.

**Milestones:**

1. **Network Tuning:** Configure CycloneDDS XML profiles for Wi-Fi degradation. Ensure packet drops do not sever the Node.js MCP connection to the ROS 2 hardware.  
2. **Safety Grounding:** Validate hardware-level interrupts (e.g., E-stops, bumper sensors). Ensure the Python Aggregation Layer can intercept these and force an LLM context update.  
3. **Physical Nav2 Tuning:** Ensure the async navigation tools translate accurately to physical hardware execution, accounting for real-world odometry drift.

**Exit Criteria:** The physical robot navigates a room, avoids physical obstacles, and responds to natural language commands with the same reliability as the simulation.

## **Phase 3: Edge AI & High-Frequency Inference**

**Objective:** Integrate heavy compute models for dynamic vision and anomaly detection.

**Milestones:**

1. **Local LLM Migration:** Transition from cloud APIs (Gemini/Claude) to local Nvidia NIM containers on the Base Station to eliminate internet dependency and reduce latency.  
2. **Deep Learning Pipeline:** Deploy DeepStream/TensorRT containers.  
3. **Aggregation Layer Integration:** Connect the high-frequency telemetry output of the DeepStream pipeline to the Python State Cache.  
4. **Complex Agentic Tasks:** Test complex tool chaining workflows (e.g., "Find the red cup, track it, and tell me if it falls off the table").

**Exit Criteria:** A fully autonomous, internet-independent robotic system capable of real-time semantic reasoning and high-frequency visual interrupt handling.