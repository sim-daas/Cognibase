/**
 * MCP tool definitions and handler. Mirrors OpenClaw adapter tools.
 */

import fs from "node:fs";
import path from "node:path";
import os from "node:os";

import type { AgenticROSConfig } from "@agenticros/core";
import { toNamespacedTopic } from "@agenticros/core";
import { getTransport } from "./transport.js";
import { checkPublishSafety } from "./safety.js";
import { getDepthDistance } from "./depth.js";

const COMPRESSED_IMAGE_TYPE = "sensor_msgs/msg/CompressedImage";
const IMAGE_TYPE = "sensor_msgs/msg/Image";
const DEFAULT_DEPTH_TOPIC = "/camera/camera/depth/image_rect_raw";

function imageDataToBase64(data: unknown): string {
  if (data == null) return "";
  if (typeof data === "string") return data;
  if (data instanceof Uint8Array) return Buffer.from(data).toString("base64");
  if (Array.isArray(data)) {
    const bytes = new Uint8Array(data.length);
    for (let i = 0; i < data.length; i++) bytes[i] = Number(data[i]) & 0xff;
    return Buffer.from(bytes).toString("base64");
  }
  throw new Error("Image data must be string (base64), Uint8Array, or array of bytes");
}

export interface McpTool {
  name: string;
  description: string;
  inputSchema: {
    type: "object";
    properties?: Record<string, { type: string; description?: string; default?: unknown }>;
    required?: string[];
  };
}

export const TOOLS: McpTool[] = [
  {
    name: "ros2_list_topics",
    description:
      "Lists all active ROS2 topics currently registered in the system's computation graph, along with their associated message types. Use this as your primary discovery tool to determine what sensors (lasers, cameras, IMUs) are available and which command interfaces (motor controllers, planning topics) you can interact with. It is essential to call this whenever you are unsure about the robot's current namespace or hardware configuration, as it provides the ground truth of the robot's capabilities in the real world.",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "ros2_list_services",
    description:
      "Retrieves a comprehensive list of all synchronous ROS2 services currently running across all nodes. Services are used for request-response patterns where you need an immediate confirmation or specific piece of data that isn't streamed continuously. Use this to find management interfaces, such as resetting odometry, spawning objects in a simulation environment, or triggering specific one-off hardware calibrations. Knowing the available services allows you to perform deterministic state changes on the robot.",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "ros2_list_actions",
    description:
      "Lists all available ROS2 action servers and their associated types. Actions are designed for long-running, preemptible tasks that provide feedback, such as autonomous navigation (Nav2), moving a robotic arm to a specific joint configuration, or executing complex mission sequences. Use this tool to discover high-level behaviors that the robot can perform autonomously without you needing to manage low-level motor commands. This is the preferred way to move the robot over significant distances.",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "ros2_list_nodes",
    description:
      "Provides a snapshot of all active process nodes within the ROS2 ecosystem. This gives you a high-level view of the robot's internal 'org chart', showing which subsystems (like localization, perception, or hardware drivers) are currently operational. Use this for diagnostic purposes or to identify which node to target for parameter changes. If a capability seems missing from the topic list, check the node list to see if the required driver or processing node is actually running.",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "ros2_vla_query",
    description:
      "Invokes a state-of-the-art Vision-Language-Action (VLA) model (qwen3-vl) to reason about the robot's current visual surroundings. IMPORTANT: This tool AUTOMATICALLY captures a fresh camera frame before processing; you do NOT need to call ros2_camera_snapshot beforehand unless you specifically want to provide a separate image to the human user's interface. Use this tool when you need to answer semantic questions about the environment, such as 'Is there a person in the doorway?', 'What color is the object on the table?', or 'Is the path ahead obstructed by any hazardous materials?'. The model will return a natural language description based on your prompt.",
    inputSchema: {
      type: "object",
      properties: {
        topic: {
          type: "string",
          description: "The specific camera image topic to sample from. By default, it uses the primary compressed image stream (/camera/image_raw/compressed). Use high-resolution topics for fine-grained detail or specialized cameras (e.g., thermal, depth) if available in the topic list.",
        },
        prompt: {
          type: "string",
          description: "A clear, descriptive question or instruction for the VLA model. Be specific about what you want to identify or analyze (e.g. 'Tell me if the red fire extinguisher is in its regular bracket' or 'Identify all humans in the frame and describe their posture').",
        },
        timeout: {
          type: "number",
          description: "Maximum time in milliseconds to wait for the image capture and model inference. Default is 60,000ms. Increase this for complex prompts or high-latency network conditions.",
        },
      },
      required: ["prompt"],
    },
  },
  {
    name: "ros2_publish",
    description:
      "Sends a message directly to a ROS2 topic. This is the primary tool for low-level control and manual intervention. Use it to send velocity commands (geometry_msgs/msg/Twist) to /cmd_vel, trigger specific state transitions in ROS nodes, or broadcast information to other systems. You must specify the exact topic name, the formal ROS2 message type string, and a JSON object representing the message payload. Be extremely careful when publishing to command topics, as this has immediate physical consequences for the robot's movement and state.",
    inputSchema: {
      type: "object",
      properties: {
        topic: {
          type: "string",
          description: "The fully qualified ROS2 topic name (e.g., '/cmd_vel'). Reference the ros2_list_topics output for exact names and namespaces.",
        },
        type: {
          type: "string",
          description: "The official ROS2 message type string (e.g., 'geometry_msgs/msg/Twist'). The message structure in the next field must match this type exactly.",
        },
        message: {
          type: "object",
          description: "The message contents, formatted as a JSON object that matches the ROS2 message structure. For example, for a Twist message: { 'linear': { 'x': 0.1, 'y': 0.0, 'z': 0.0 }, 'angular': { 'x': 0.0, 'y': 0.0, 'z': 0.0 } }.",
        },
      },
      required: ["topic", "type", "message"],
    },
  },
  {
    name: "ros2_subscribe_once",
    description:
      "Performs a one-time subscription to a ROS2 topic and returns the very next message received. This is your primary way to 'read' the current state of sensors or robot telemetry without continuous streaming. Use this to check battery levels, obtain the current GPS/Odometry pose, or verify that a command has been received by checking its corresponding feedback topic. It handles the connection and cleanup automatically. If the topic is an image and you need visual reasoning, use ros2_vla_query instead for better efficiency.",
    inputSchema: {
      type: "object",
      properties: {
        topic: {
          type: "string",
          description: "The ROS2 topic to listen to (e.g., '/battery_state', '/odom'). Ensure the topic is currently active in the system.",
        },
        type: {
          type: "string",
          description: "The ROS2 message type (optional). Providing this helps the tool subscribe more reliably if the system cannot auto-detect the type from the topic name.",
        },
        timeout: {
          type: "number",
          description: "How long to wait for a message to arrive in milliseconds. Default is 1,500ms. Increase for slow-publishing sensors like low-frequency environmental monitors.",
        },
      },
      required: ["topic"],
    },
  },
  {
    name: "ros2_service_call",
    description:
      "Makes a synchronous call to a ROS2 service and waits for the response. Services are for discrete operations that require a result, unlike topics which are for streaming. Use this to toggle hardware features (e.g. 'enable_lidar'), request path planning from a global planner, or clear costmaps in Nav2. The tool returns the service's response payload as a stringified JSON object. If the service call fails or times out, an error is returned describing the interruption.",
    inputSchema: {
      type: "object",
      properties: {
        service: {
          type: "string",
          description: "The name of the service to call (e.g., '/spawn_entity', '/reset_pose'). Verify available services via ros2_list_services.",
        },
        type: {
          type: "string",
          description: "The ROS2 service type (e.g., 'turtlesim/srv/TeleportAbsolute'). Providing this ensures the request is formatted correctly for the server node.",
        },
        args: {
          type: "object",
          description: "An object containing the service request parameters, matching the service definition's field names and data types.",
        },
      },
      required: ["service"],
    },
  },
  {
    name: "ros2_action_goal",
    description:
      "Dispatches a long-running task to a ROS2 Action Server. Actions are 'stateful' goals that can take time to complete, such as driving to a coordinate. This tool starts the goal and returns the immediate status (and eventually the result). Use this for navigation tasks where you want the robot to manage its own pathfinding and obstacle avoidance. The goal parameter must contain the specific instructions for that action (e.g., the target coordinate for navigation). You can trigger multiple actions, though typically a robot can only follow one spatial goal at a time.",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          description: "The name of the action server (e.g., '/navigate_to_pose'). Use ros2_list_actions to find what behaviors are currently available.",
        },
        actionType: {
          type: "string",
          description: "The ROS2 action type string (e.g., 'nav2_msgs/action/NavigateToPose'). This defines the structure of the goal payload.",
        },
        goal: {
          type: "object",
          description: "The action goal payload. For NavigateToPose, this is typically a PoseStamped message containing the target X/Y coordinates and heading.",
        },
      },
      required: ["action", "actionType", "goal"],
    },
  },
  {
    name: "ros2_param_get",
    description:
      "Retrieves the current value of a configuration parameter from a specific ROS2 node. Parameters control the behavior of nodes at runtime, such as the 'max_vel_x' of a controller or 'inflation_radius' of a costmap. Use this tool to inspect the robot's current configuration or to verify that a ros2_param_set call was successful. Knowing the internal parameters allows you to understand why the robot is behaving in a certain way (e.g. why it refuses to drive faster).",
    inputSchema: {
      type: "object",
      properties: {
        node: {
          type: "string",
          description: "The fully qualified path to the node owning the parameter (e.g., '/controller_server').",
        },
        parameter: {
          type: "string",
          description: "The specific name of the parameter you wish to read (e.g., 'max_velocity', 'use_sim_time').",
        },
      },
      required: ["node", "parameter"],
    },
  },
  {
    name: "ros2_param_set",
    description:
      "Modifies a configuration parameter on a live ROS2 node. This allows you to tune the robot's hardware or software on the fly without restarting any processes. Use this to adjust speed limits, change sensor configurations, or toggle safety features. Note that not all parameters can be changed at runtime; some are 'read-only' after initialization. Always verify the change with ros2_param_get if the robot doesn't immediately respond as expected.",
    inputSchema: {
      type: "object",
      properties: {
        node: { type: "string", description: "The fully qualified node name." },
        parameter: { type: "string", description: "The name of the parameter to change." },
        value: {
          type: "object",
          description: "The new value for the parameter. Use the appropriate JSON type (string, number, boolean, or array) that matches the parameter's expected type.",
        },
      },
      required: ["node", "parameter", "value"],
    },
  },
  {
    name: "ros2_camera_snapshot",
    description:
      "Captures a single, discrete image frame from a camera stream and transmits it to the user interface. This tool is primarily for the human operator to see what the robot is seeing and for archival/logging purposes. It supports both standard raw images and compressed streams (JPEG/PNG). Use this when the user explicitly asks for a 'photo' or 'to see the view'. If you need the robot system to REASON about what it sees, use ros2_vla_query instead, as it provides you with a textual description of the image content.",
    inputSchema: {
      type: "object",
      properties: {
        topic: {
          type: "string",
          description: "The camera topic to capture (default: /camera/image_raw/compressed). Check ros2_list_topics to see available vantage points.",
        },
        message_type: {
          type: "string",
          description: "The format of the source stream: 'CompressedImage' or 'Image'. Default is CompressedImage.",
        },
        timeout: {
          type: "number",
          description: "How long to wait for a frame to be received in milliseconds. Default 10,000ms.",
        },
      },
    },
  },
  {
    name: "ros2_depth_distance",
    description:
      "Samples the central region of a depth camera image to provide a precise distance measurement to the nearest physical surface in meters. This is functionally a virtual laser rangefinder or sonar sensor. Use this when you need a quantitative answer to 'How far away is that person?' or 'Is there enough clearance to turn around?'. It is far more precise for spatial tasks than visual estimation via the VLA tool. It automatically handles typical depth encodings (16UC1, 32FC1).",
    inputSchema: {
      type: "object",
      properties: {
        topic: {
          type: "string",
          description: `The depth image topic to query (default: ${DEFAULT_DEPTH_TOPIC}). It must be a depth stream, not a standard color stream.`,
        },
        timeout: {
          type: "number",
          description: "Timeout in milliseconds for the subscription. Default 5,000ms.",
        },
      },
    },
  },
  {
    name: "ros2_cmd_vel_duration",
    description:
      "Executes a persistent velocity command (Twist) for a controlled amount of time. Standard ROS2 /cmd_vel publishers usually require a high-frequency stream to prevent the robot's safety hardware from timing out and stopping the motors. This tool handles that complexity for you by publishing at 10Hz for the specified duration. Use this for short, precise movements (e.g. 'rotate 90 degrees', 'pull forward by 0.5m') or when navigation isn't running and you need to clear an obstacle manually. Use positive linear_x for forward, negative for backward, and angular_z for rotation (positive is counter-clockwise).",
    inputSchema: {
      type: "object",
      properties: {
        topic: {
          type: "string",
          description: "The velocity controller topic. Usually '/cmd_vel'. Use the list tool to verify if the robot uses a different command topic.",
        },
        linear_x: {
          type: "number",
          description: "Forward (+) or backward (-) velocity in meters per second. Max recommended 0.22.",
        },
        angular_z: {
          type: "number",
          description: "Rotational velocity in radians per second. Positive is counter-clockwise. Max recommended 2.84.",
        },
        duration: {
          type: "number",
          description: "The time in seconds to keep the robot moving at this velocity. The command will automatically stop (sending zero velocity) once this time elapses.",
        },
      },
      required: ["linear_x", "angular_z", "duration"],
    },
  },
  {
    name: "ros2_query_state",
    description:
      "Provides a comprehensive, high-level snapshot of the robot's current physical state by aggregating data from multiple key topics (/odom, /scan, /cmd_vel). This is your primary diagnostic tool to understand where the robot is, how fast it's moving, and what obstacles are nearby. It processes high-density sensor data (like LIDAR scans) into a simplified, 8-directional 'radar' view (Front, Back, Left, Right, and diagonals) showing the minimum distance to obstacles in each sector. Use this frequently for spatial awareness, safety checks, and to verify that motion commands are having the intended effect. All topics are queried in parallel for maximum efficiency.",
    inputSchema: { type: "object", properties: {} },
  },
];

export type ToolContent = { type: "text"; text: string } | { type: "image"; data: string; mimeType: string };

export async function handleToolCall(
  name: string,
  args: Record<string, unknown>,
  config: AgenticROSConfig,
): Promise<{ content: ToolContent[]; isError?: boolean }> {
  const transport = getTransport();

  switch (name) {
    case "ros2_list_topics": {
      const topics = await transport.listTopics();
      const MAX = 50;
      const truncated = topics.length > MAX ? topics.slice(0, MAX) : topics;
      const text = JSON.stringify({
        success: true,
        topics: truncated,
        total: topics.length,
        truncated: topics.length > MAX,
      });
      return { content: [{ type: "text", text }] };
    }

    case "ros2_list_services": {
      const services = await transport.listServices();
      const MAX = 50;
      const truncated = services.length > MAX ? services.slice(0, MAX) : services;
      const text = JSON.stringify({
        success: true,
        services: truncated,
        total: services.length,
        truncated: services.length > MAX,
      });
      return { content: [{ type: "text", text }] };
    }

    case "ros2_list_actions": {
      const actions = await transport.listActions();
      const MAX = 50;
      const truncated = actions.length > MAX ? actions.slice(0, MAX) : actions;
      const text = JSON.stringify({
        success: true,
        actions: truncated,
        total: actions.length,
        truncated: actions.length > MAX,
      });
      return { content: [{ type: "text", text }] };
    }

    case "ros2_list_nodes": {
      const response = await transport.callService({
        service: "/rosapi/nodes",
        type: "rosapi/srv/Nodes",
      });
      const nodes = Array.isArray(response.values?.["nodes"]) ? response.values!["nodes"] as string[] : [];
      const MAX = 50;
      const truncated = nodes.length > MAX ? nodes.slice(0, MAX) : nodes;
      const text = JSON.stringify({
        success: response.result,
        nodes: truncated,
        total: nodes.length,
        truncated: nodes.length > MAX,
      });
      return { content: [{ type: "text", text }] };
    }

    case "ros2_vla_query": {
      const defaultTopic = "/camera/image_raw/compressed";
      const rawTopic = (args["topic"] as string | undefined) ?? defaultTopic;
      const topic = toNamespacedTopic(config, rawTopic);
      const prompt = args["prompt"] as string;
      const timeout = (args["timeout"] as number | undefined) ?? 60000;
      const messageType: "CompressedImage" | "Image" = topic.includes("compressed") ? "CompressedImage" : "Image";
      const type = messageType === "Image" ? IMAGE_TYPE : COMPRESSED_IMAGE_TYPE;

      // 1. Capture image
      const imageResult = await new Promise<Record<string, unknown>>((resolve, reject) => {
        const subscription = transport.subscribe(
          { topic, type },
          (msg: Record<string, unknown>) => {
            clearTimeout(timer);
            subscription.unsubscribe();
            if (messageType === "Image") {
              const data = msg["data"];
              resolve({ success: true, data: imageDataToBase64(data) });
            } else {
              const raw = msg["data"];
              resolve({ success: true, data: typeof raw === "string" ? raw : imageDataToBase64(raw) });
            }
          },
        );
        const timer = setTimeout(() => {
          subscription.unsubscribe();
          reject(new Error(`Timeout waiting for camera frame on ${topic}`));
        }, 10000);
      });

      const base64Image = imageResult.data as string;
      if (!base64Image) {
        return { content: [{ type: "text", text: "Failed to capture image for VLA query." }], isError: true };
      }

      // 2. Query NVIDIA NIM VLA endpoint
      let nvidiaApiKey = process.env.NVIDIA_API_KEY;

      if (!nvidiaApiKey) {
        // Fallback: try to load from config/cognibot.env relative to workspace or known paths
        const envPaths = [
          "/app/config/cognibot.env",
          path.resolve(process.cwd(), "config/cognibot.env"),
          path.resolve(process.cwd(), "../../config/cognibot.env"),
          path.resolve(os.homedir(), ".agenticros/cognibot.env"),
        ];

        for (const envPath of envPaths) {
          try {
            if (fs.existsSync(envPath)) {
              const content = fs.readFileSync(envPath, "utf8");
              const match = content.match(/^NVIDIA_API_KEY\s*=\s*(.*)$/m);
              if (match && match[1]) {
                nvidiaApiKey = match[1].trim();
                break;
              }
            }
          } catch (e) {}
        }
      }
      const nvidiaUrl = "https://integrate.api.nvidia.com/v1/chat/completions";
      const vlaModel = "nvidia/nemotron-nano-12b-v2-vl";

      if (!nvidiaApiKey) {
        return { content: [{ type: "text", text: "VLA reasoning failed: NVIDIA_API_KEY environment variable is not set." }], isError: true };
      }

      // Detect image format from topic name; default to jpeg for compressed streams
      const imageMediaType = messageType === "Image" ? "image/png" : "image/jpeg";

      try {
        const controller = new AbortController();
        const fetchTimer = setTimeout(() => controller.abort(), timeout);

        const response = await fetch(nvidiaUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": `Bearer ${nvidiaApiKey}`,
          },
          body: JSON.stringify({
            model: vlaModel,
            stream: false,
            max_tokens: 512,
            messages: [
              {
                role: "user",
                content: [
                  { type: "text", text: prompt },
                  { type: "image_url", image_url: { url: `data:${imageMediaType};base64,${base64Image}` } }
                ]
              }
            ]
          }),
          signal: controller.signal,
        });

        clearTimeout(fetchTimer);

        if (!response.ok) {
          const errText = await response.text().catch(() => response.statusText);
          throw new Error(`NVIDIA API error: ${response.status} ${errText}`);
        }

        const data = await response.json() as Record<string, unknown>;
        let output = "No response generated";
        const choices = data.choices as Array<Record<string, unknown>> | undefined;
        if (choices && choices.length > 0) {
          const msg = choices[0].message as Record<string, unknown> | undefined;
          if (msg) output = String(msg.content || output);
        }
        return { content: [{ type: "text", text: `[VLA Output via ${topic} | ${vlaModel}]:\n${output}` }] };
      } catch (err: any) {
        const msg = err instanceof Error ? err.message : String(err);
        const cause = err.cause ? ` (Cause: ${err.cause.message || err.cause})` : "";
        return { content: [{ type: "text", text: `VLA reasoning failed: ${msg}${cause} [Attempted: ${nvidiaUrl}]` }], isError: true };
      }

    }

    case "ros2_publish": {
      const rawTopicIn = String(args["topic"] ?? "").trim();
      if (process.stderr?.write) {
        process.stderr.write(`[AgenticROS] ros2_publish called topic=${JSON.stringify(rawTopicIn)}\n`);
      }
      if (transport.getStatus() !== "connected") {
        if (process.stderr?.write) {
          process.stderr.write(`[AgenticROS] ros2_publish abort: transport not connected\n`);
        }
        return {
          content: [{ type: "text", text: "Transport not connected. Check rosbridge_server is running (ws://localhost:9090) and agenticros config (config/agenticros.json). See MCP adapter logs for details." }],
          isError: true,
        };
      }
      const safe = checkPublishSafety(config, args);
      if (safe.block) {
        return { content: [{ type: "text", text: safe.blockReason ?? "Blocked by safety." }], isError: true };
      }
      // Unconditionally rewrite /<uuid>/cmd_vel → /robot<uuid-no-dashes>/cmd_vel (robot often expects UUID without dashes)
      const cmdVelMatch = rawTopicIn.match(/^\/([^/]+)\/cmd_vel$/i);
      const segment = cmdVelMatch?.[1] ?? "";
      const topic =
        cmdVelMatch && !segment.toLowerCase().startsWith("robot")
          ? `/robot${segment.replace(/-/g, "")}/cmd_vel`
          : toNamespacedTopic(config, rawTopicIn);
      if (process.stderr?.write) {
        process.stderr.write(`[AgenticROS] ros2_publish: → topic=${topic}\n`);
      }
      const type = args["type"] as string;
      const message = args["message"] as Record<string, unknown>;

      // Explicitly advertise before publish for Jazzy rosbridge compatibility
      if (transport.advertise) {
        transport.advertise({ topic, type });
      }

      const PUBLISH_TIMEOUT_MS = 10_000;
      const timeoutPromise = new Promise<never>((_, reject) => {
        setTimeout(() => reject(new Error("Publish timed out after " + PUBLISH_TIMEOUT_MS / 1000 + "s. Check rosbridge_server is running and reachable.")), PUBLISH_TIMEOUT_MS);
      });
      try {
        await Promise.race([transport.publish({ topic, type, msg: message }), timeoutPromise]);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        return { content: [{ type: "text", text: `Publish failed: ${msg}` }], isError: true };
      }
      const summary = cmdVelMatch && topic.startsWith("/robot") ? `Published to ${topic} (robot prefix applied).` : `Published to ${topic}.`;
      return { content: [{ type: "text", text: summary + "\n" + JSON.stringify({ success: true, topic, type }) }] };
    }

    case "ros2_subscribe_once": {
      const rawTopic = args["topic"] as string;
      const topic = toNamespacedTopic(config, rawTopic);
      let msgType = args["type"] as string | undefined;
      const timeout = (args["timeout"] as number | undefined) ?? 1500;
      if (!msgType && /\/?(camera|image|color|depth)/i.test(rawTopic)) {
        msgType = rawTopic.includes("compressed") ? "sensor_msgs/msg/CompressedImage" : "sensor_msgs/msg/Image";
      }
      const result = await new Promise<Record<string, unknown>>((resolve, reject) => {
        const sub = transport.subscribe(
          { topic, type: msgType },
          (msg: Record<string, unknown>) => {
            clearTimeout(timer);
            sub.unsubscribe();
            resolve({ success: true, topic, message: msg });
          },
        );
        const timer = setTimeout(() => {
          sub.unsubscribe();
          reject(new Error(`Timeout waiting for message on ${topic}`));
        }, timeout);
      });
      let text = JSON.stringify(result);
      const MAX_CHARS = 8000;
      if (text.length > MAX_CHARS) {
        text = JSON.stringify({
          success: true,
          topic,
          message: "[truncated: message too large]",
          originalSize: text.length,
        }) + "\n(Use ros2_camera_snapshot for image topics.)";
      }
      return { content: [{ type: "text", text }] };
    }

    case "ros2_service_call": {
      const rawService = args["service"] as string;
      const service = toNamespacedTopic(config, rawService);
      const type = args["type"] as string | undefined;
      const reqArgs = args["args"] as Record<string, unknown> | undefined;
      const response = await transport.callService({ service, type, args: reqArgs });
      const text = JSON.stringify({
        success: response.result,
        service,
        response: response.values,
      });
      return { content: [{ type: "text", text }] };
    }

    case "ros2_action_goal": {
      const rawAction = args["action"] as string;
      const action = toNamespacedTopic(config, rawAction);
      const actionType = args["actionType"] as string;
      const goal = args["goal"] as Record<string, unknown>;
      const actionResult = await transport.sendActionGoal({ action, actionType, args: goal });
      const text = JSON.stringify({
        success: actionResult.result,
        action,
        result: actionResult.values,
      });
      return { content: [{ type: "text", text }] };
    }

    case "ros2_param_get": {
      const rawNode = args["node"] as string;
      const node = toNamespacedTopic(config, rawNode);
      const parameter = args["parameter"] as string;
      const response = await transport.callService({
        service: `${node}/get_parameters`,
        type: "rcl_interfaces/srv/GetParameters",
        args: { names: [parameter] },
      });
      const text = JSON.stringify({
        success: response.result,
        node,
        parameter,
        value: response.values,
      });
      return { content: [{ type: "text", text }] };
    }

    case "ros2_param_set": {
      const rawNode = args["node"] as string;
      const node = toNamespacedTopic(config, rawNode);
      const parameter = args["parameter"] as string;
      const value = args["value"];
      const response = await transport.callService({
        service: `${node}/set_parameters`,
        type: "rcl_interfaces/srv/SetParameters",
        args: { parameters: [{ name: parameter, value }] },
      });
      const text = JSON.stringify({
        success: response.result,
        node,
        parameter,
      });
      return { content: [{ type: "text", text }] };
    }

    case "ros2_camera_snapshot": {
      const defaultTopic =
        (config.robot?.cameraTopic ?? "").trim() || "/camera/camera/color/image_raw/compressed";
      const rawTopic = (args["topic"] as string | undefined) ?? defaultTopic;
      const topic = toNamespacedTopic(config, rawTopic);
      const rawMsgType = args["message_type"] as string | undefined;
      const messageType: "CompressedImage" | "Image" = rawMsgType === "Image" ? "Image" : "CompressedImage";
      const timeout = (args["timeout"] as number | undefined) ?? 10000;
      const type = messageType === "Image" ? IMAGE_TYPE : COMPRESSED_IMAGE_TYPE;

      const result = await new Promise<Record<string, unknown>>((resolve, reject) => {
        const subscription = transport.subscribe(
          { topic, type },
          (msg: Record<string, unknown>) => {
            clearTimeout(timer);
            subscription.unsubscribe();
            if (messageType === "Image") {
              const data = msg["data"];
              const encoding = (msg["encoding"] as string) ?? "rgb8";
              resolve({
                success: true,
                topic,
                format: encoding,
                data: imageDataToBase64(data),
                width: msg["width"],
                height: msg["height"],
              });
            } else {
              const raw = msg["data"];
              resolve({
                success: true,
                topic,
                format: msg["format"] ?? "jpeg",
                data: typeof raw === "string" ? raw : imageDataToBase64(raw),
              });
            }
          },
        );
        const timer = setTimeout(() => {
          subscription.unsubscribe();
          reject(new Error(`Timeout waiting for camera frame on ${topic}`));
        }, timeout);
      });

      const base64 = (result.data as string) ?? "";
      const format = String((result.format as string) ?? "jpeg").toLowerCase();
      const mimeType =
        format === "png" ? "image/png" : format === "gif" ? "image/gif" : format === "webp" ? "image/webp" : "image/jpeg";
      const summary = `Captured one frame from ${topic}${result.width != null ? ` (${result.width}×${result.height})` : ""}.`;
      const content: ToolContent[] = [{ type: "text", text: summary }];
      if (base64 && /^[A-Za-z0-9+/=]+$/.test(base64) && base64.length >= 100) {
        content.push({ type: "image", data: base64, mimeType });
      } else if (!base64) {
        content.push({
          type: "text",
          text: " (No image data received—topic may be idle or transport returned empty.)",
        });
      }
      return { content };
    }

    case "ros2_depth_distance": {
      const rawTopic = (args["topic"] as string | undefined)?.trim() || DEFAULT_DEPTH_TOPIC;
      const topic = toNamespacedTopic(config, rawTopic);
      const timeout = (args["timeout"] as number | undefined) ?? 5000;
      try {
        const result = await getDepthDistance(transport, topic, timeout);
        const text = result.valid
          ? `Distance at center of depth image: **${result.distance_m} m** (range in sample: ${result.min_m}–${result.max_m} m, ${result.sample_count} pixels). Topic: ${result.topic}.`
          : `No valid depth in center region (topic: ${result.topic}, ${result.width}×${result.height}, encoding ${result.encoding}).`;
        return { content: [{ type: "text", text }] };
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        return {
          content: [{ type: "text", text: `Depth distance failed: ${message}` }],
          isError: true,
        };
      }
    }

    case "ros2_cmd_vel_duration": {
      const rawTopicIn = String(args["topic"] ?? "/cmd_vel").trim();
      
      // 1. Sync with ros2_publish logic for robot prefix rewriting
      const cmdVelMatch = rawTopicIn.match(/^\/([^/]+)\/cmd_vel$/i);
      const segment = cmdVelMatch?.[1] ?? "";
      const topic =
        cmdVelMatch && !segment.toLowerCase().startsWith("robot")
          ? `/robot${segment.replace(/-/g, "")}/cmd_vel`
          : toNamespacedTopic(config, rawTopicIn);

      // 2. Detect topic type (Twist vs TwistStamped)
      let type = "geometry_msgs/msg/Twist";
      try {
        const activeTopics = await transport.listTopics();
        const found = activeTopics.find(t => t.name === topic);
        if (found && found.type.includes("TwistStamped")) {
          type = found.type;
        }
      } catch (e) {
        if (process.stderr?.write) process.stderr.write(`[AgenticROS] Topic type detection failed: ${e}\n`);
      }

      const linear_x = Number(args["linear_x"] ?? 0);
      const linear_y = Number(args["linear_y"] ?? 0);
      const angular_z = Number(args["angular_z"] ?? 0);
      const duration = Number(args["duration"] ?? 1);

      const twistMsg = {
        linear: { x: linear_x, y: linear_y, z: 0.0 },
        angular: { x: 0.0, y: 0.0, z: angular_z }
      };

      const isStamped = type.includes("TwistStamped");
      const message = isStamped 
        ? { header: { stamp: { sec: 0, nanosec: 0 }, frame_id: "" }, twist: twistMsg }
        : twistMsg;

      const safe = checkPublishSafety(config, {
        topic,
        type,
        message: isStamped ? (message as any).twist : message
      });
      if (safe.block) {
        return { content: [{ type: "text", text: safe.blockReason ?? "Blocked by safety." }], isError: true };
      }

      if (process.stderr?.write) {
        process.stderr.write(`[AgenticROS] ros2_cmd_vel_duration: topic=${topic} type=${type} v=(${linear_x},${linear_y}) w=${angular_z} t=${duration}s\n`);
      }

      // 3. Explicitly advertise before publish for Jazzy rosbridge compatibility
      if (transport.advertise) {
        transport.advertise({ topic, type });
      }

      await new Promise<void>((resolve) => {
        const endTime = Date.now() + duration * 1000;
        const interval = setInterval(async () => {
          if (Date.now() >= endTime) {
            clearInterval(interval);
            // End with zero velocity
            try {
              const stopTwist = { linear: { x: 0, y: 0, z: 0 }, angular: { x: 0, y: 0, z: 0 } };
              const stopMsg = isStamped 
                ? { header: { stamp: { sec: 0, nanosec: 0 }, frame_id: "" }, twist: stopTwist }
                : stopTwist;
              await transport.publish({ topic, type, msg: stopMsg });
            } catch (e) {
              if (process.stderr?.write) process.stderr.write(`[AgenticROS] cmd_vel_duration stop-publish failed: ${e}\n`);
            }
            resolve();
            return;
          }
          try {
            // Update timestamp if stamped
            if (isStamped) {
              const now = Date.now();
              (message as any).header.stamp = {
                sec: Math.floor(now / 1000),
                nanosec: (now % 1000) * 1000000
              };
            }
            await transport.publish({ topic, type, msg: message });
          } catch (e) {
            if (process.stderr?.write) process.stderr.write(`[AgenticROS] cmd_vel_duration publish failed: ${e}\n`);
          }
        }, 100);
      });

      return { content: [{ type: "text", text: `Successfully published ${isStamped ? 'TwistStamped' : 'Twist'} velocity to ${topic} for ${duration} seconds.` }] };
    }

    case "ros2_query_state": {
      const topics = await transport.listTopics();
      const targetTopics = ["/odom", "/scan", "/cmd_vel"];
      const activeTopics = topics.filter((t) => targetTopics.includes(t.name));
      const timeout = 1500;

      const stateRecords: Record<string, any> = {
        timestamp: new Date().toISOString(),
        active_topics: activeTopics.map(t => t.name)
      };

      const promises: Promise<void>[] = activeTopics.map(async (t) => {
        const topic = toNamespacedTopic(config, t.name);
        try {
          const result = await new Promise<any>((resolve, reject) => {
            const sub = transport.subscribe({ topic, type: t.type }, (msg) => {
              clearTimeout(timer);
              sub.unsubscribe();
              resolve(msg);
            });
            const timer = setTimeout(() => {
              sub.unsubscribe();
              reject(new Error("Timeout"));
            }, timeout);
          });

          // Process based on topic name
          if (t.name === "/scan") {
            const ranges = (result.ranges as number[]) || [];
            const angleMin = result.angle_min || 0;
            const angleInc = result.angle_increment || (2 * Math.PI) / ranges.length;
            
            const sectors: Record<string, number> = {
              Front: Infinity, Front_Left: Infinity, Left: Infinity, Back_Left: Infinity,
              Back: Infinity, Back_Right: Infinity, Right: Infinity, Front_Right: Infinity
            };

            ranges.forEach((dist, i) => {
              if (dist === null || isNaN(dist) || dist <= 0) return;
              let angle = angleMin + i * angleInc;
              // Normalize to [0, 2PI)
              angle = ((angle % (2 * Math.PI)) + (2 * Math.PI)) % (2 * Math.PI);
              const deg = (angle * 180) / Math.PI;

              let sector = "";
              if (deg >= 337.5 || deg < 22.5) sector = "Front";
              else if (deg >= 22.5 && deg < 67.5) sector = "Front_Left";
              else if (deg >= 67.5 && deg < 112.5) sector = "Left";
              else if (deg >= 112.5 && deg < 157.5) sector = "Back_Left";
              else if (deg >= 157.5 && deg < 202.5) sector = "Back";
              else if (deg >= 202.5 && deg < 247.5) sector = "Back_Right";
              else if (deg >= 247.5 && deg < 292.5) sector = "Right";
              else if (deg >= 292.5 && deg < 337.5) sector = "Front_Right";

              if (sector && dist < sectors[sector]) {
                sectors[sector] = dist;
              }
            });

            // Clean up Infinity
            for (const key in sectors) {
              if (sectors[key] === Infinity) sectors[key] = -1; // -1 means no reading
              else sectors[key] = Math.round(sectors[key] * 100) / 100; // Round to 2 decimals
            }
            stateRecords.obstacles_min_dist = sectors;
          } else if (t.name === "/odom") {
            stateRecords.odom = {
              pos: {
                x: Math.round(result.pose?.pose?.position?.x * 1000) / 1000 || 0,
                y: Math.round(result.pose?.pose?.position?.y * 1000) / 1000 || 0,
                z: Math.round(result.pose?.pose?.position?.z * 1000) / 1000 || 0
              },
              ori: {
                x: Math.round(result.pose?.pose?.orientation?.x * 1000) / 1000 || 0,
                y: Math.round(result.pose?.pose?.orientation?.y * 1000) / 1000 || 0,
                z: Math.round(result.pose?.pose?.orientation?.z * 1000) / 1000 || 0,
                w: Math.round(result.pose?.pose?.orientation?.w * 1000) / 1000 || 0
              },
              vel: {
                linear: {
                  x: Math.round(result.twist?.twist?.linear?.x * 1000) / 1000 || 0,
                  y: Math.round(result.twist?.twist?.linear?.y * 1000) / 1000 || 0
                },
                angular: {
                  z: Math.round(result.twist?.twist?.angular?.z * 1000) / 1000 || 0
                }
              }
            };
          } else if (t.name === "/cmd_vel") {
            stateRecords.last_cmd_vel = {
              linear: result.linear?.x || 0,
              angular: result.angular?.z || 0
            };
          }
        } catch (e) {
          // If a topic fails, we just don't include it in stateRecords
        }
      });

      await Promise.all(promises);
      return { content: [{ type: "text", text: JSON.stringify(stateRecords, null, 2) }] };
    }

    default:
      return {
        content: [{ type: "text", text: `Unknown tool: ${name}` }],
        isError: true,
      };
  }
}
