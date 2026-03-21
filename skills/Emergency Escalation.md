## **SKILL\_ID: emergency\_escalation DESCRIPTION: Mandatory protocols for handling physical anomalies, detected falls, unauthorized access, or critical hardware failures.**

# **Skill: Emergency Escalation & Triage Protocol**

If a background interrupt fires (e.g., Fall Detected, Unrecognized Person in Server Room), you must immediately drop current tasks and execute this triage protocol.

## **1\. Visual Verification (Grounding)**

Do not trigger alarms based purely on a single sensor blip. You must achieve visual verification.

* Orient the camera to the anomaly coordinates.  
* Use capture\_camera\_frame and query\_vla\_pipeline to assess severity.  
  * *Prompt example:* "Is the person on the floor injured or moving?" or "Is the person wearing a blue contractor badge?"

## **2\. Immediate Kinetic Mitigation**

If the threat is verified:

* **Hazard/Fire/Spill:** Issue a zero-velocity command to the base. Do not drive through the hazard.  
* **Security Breach:** Use control\_appliance to secure local physical perimeters (lock doors).

## **3\. Communication Escalation**

Do not wait for the human to check the logs.

1. Use trigger\_alarm to activate local physical sirens if there is immediate life safety risk.  
2. Use send\_notification to dispatch the verified anomaly text AND the supporting camera frame to the administrator.  
3. Do not resume normal operations until the operator issues a manual "all clear" override.