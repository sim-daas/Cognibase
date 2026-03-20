# **AgenticROS MCP Tool Taxonomy**

These tools are exposed to the LLM via the Node.js MCP bridge. They abstract complex ROS 2 action servers and service calls into single, discrete operations.

## **Navigation & Movement**

1. **Maps\_to\_point**: Drive the robot to a specified spatial coordinate (x, y, theta) using Nav2.  
2. **initiate\_auto\_docking**: Override current tasks and navigate to the charging station.  
3. **track\_object**: Lock navigation and camera pan/tilt to follow a specific bounding box or ID.

## **Vision & Perception**

4. **capture\_camera\_frame**: Request a single RGB image matrix from the primary camera.  
5. **get\_3d\_depth**: Query the point cloud for the exact distance to a specific coordinate or object.  
6. **detect\_objects\_coco**: Run 2D bounding box inference for common standard objects (returns coordinates/labels).  
7. **filter\_color\_hsv**: Isolate and return bounding boxes for specific objects based on a defined HSV color spectrum.  
8. **query\_vla\_pipeline**: Send an image and a natural language query to the Vision-Language-Action model for abstract visual reasoning.  
9. **read\_text\_ocr**: Extract written text and digits from the current visual frame.  
10. **scan\_qr\_code**: Decode QR or ArUco markers in the environment for localization or data retrieval.

## **State & Kinematics**

11. **estimate\_pose**: Extract human skeletal joint coordinates from the current camera frame.  
12. **recognize\_action**: Analyze sequential frames/poses to identify human behaviors (e.g., falling, running).  
13. **read\_temperature**: Poll thermal sensors for ambient or specific hardware surface temperatures.  
14. **classify\_audio\_event**: Identify non-speech sounds (e.g., breaking glass, alarms, footsteps) via the microphone array.

## **Interaction & Communication**

15. **ask\_human\_clarification**: Synthesize text-to-speech to physically ask the operator a question via the robot's speakers.  
16. **send\_notification**: Dispatch a text message or alert payload to the human operator's device.  
17. **trigger\_alarm**: Activate physical or digital emergency sirens and strobes on the robot or facility network.  
18. **control\_appliance**: Toggle smart home devices, doors, or lab equipment via IoT relays.

## **Memory & Context**

19. **query\_semantic\_memory**: Retrieve historical context, prior states, or mapped locations from the localized database.