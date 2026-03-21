## **SKILL\_ID: visual\_search DESCRIPTION: Heuristics for finding lost or ambiguously defined objects in an open environment. Load this when asked to locate an item without known coordinates.**

# **Skill: Dynamic Visual Search Framework**

Do not guess where objects are. When instructed to find an item with no known coordinates, execute the following heuristic framework:

## **1\. Contextual Prediction**

Before moving, query query\_semantic\_memory for the last known location of the object. If unknown, use logical inference. (e.g., A "toolkit" belongs in the garage; a "blue bottle" belongs in a kitchen or on a desk).

## **2\. Waypoint Exploration**

Publish sequential navigation goals to Maps\_to\_point targeting the predicted areas.

* **Rule of Halts:** Do not attempt to process vision while the base is moving. Reach the waypoint, achieve zero velocity, and then poll the sensors.

## **3\. Tool Selection Hierarchy**

Execute vision tools in order of computational efficiency:

1. **Fast/Cheap:** Use detect\_objects\_coco or filter\_color\_hsv if the object fits standard taxonomy (e.g., "person", "bottle", "red ball").  
2. **Slow/Expensive:** If the object is semantically complex (e.g., "the box with the fragile sticker"), use capture\_camera\_frame and pass it to query\_vla\_pipeline.

## **4\. Failure Protocol**

If an area is exhausted, move to the next logical waypoint. If all logical waypoints are exhausted, immediately use ask\_human\_clarification or send\_notification stating: "Search matrix exhausted. Item not detected in primary zones."