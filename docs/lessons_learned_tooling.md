# Lessons Learned: CogniBot Tool Integration & Debugging

This summary captures the core issues resolved and the standardized workflow for adding tools to the CogniBot (Python) and AgenticROS (Node.js/MCP) system.

## **1. Critical Architectural Fixes**

### **A. PydanticAI Schema Binding**
*   **Problem**: Using the default `Tool(fn)` constructor failed to pass the JSON Schema to the LLM. The agent was "blind" to tool parameters (like `topic` or `linear_x`), leading to empty calls.
*   **Solution**: Always use `Tool.from_schema()` in `cognibot/agent.py`.
*   **Code Pattern**:
    ```python
    return Tool.from_schema(
        mcp_tool_proxy,
        name=tool_name,
        description=description,
        json_schema=parameters_schema,  # Required for parameter visibility
        takes_ctx=True,
    )
    ```

### **B. Environment Propagation to Subprocesses**
*   **Problem**: The MCP server (Node.js) is a subprocess of the Agent (Python). Variables like `OLLAMA_BASE_URL` in `.env` were not inherited by Node by default.
*   **Solution**: Explicitly add required host variables to the `mcp_env` dictionary in `cognibot/config.py`.

---

## **2. Standard Tool Addition Workflow**

1.  **Interface Definition**: Add the tool and its `inputSchema` to the `TOOLS` array in `agenticros/packages/agenticros-claude-code/src/tools.ts`.
2.  **Implementation**: Add the execution logic in the `handleToolCall` switch-case.
3.  **VLA Specifics**: 
    *   Use the `/api/chat` endpoint and `messages` format for Qwen/multimodal models.
    *   Ensure the model name matches exactly (e.g., `qwen3-vl`).
4.  **Container Build**: Always recompile the TypeScript code **inside the container**:
    ```bash
    docker exec -w /app/agenticros cognibot_orchestrator pnpm run build
    ```

---

## **3. Debugging within the TUI**

*   **Issue**: The TUI hides standard error streams, making "fetch errors" hard to diagnose.
*   **Solution**: In the tool's `catch` block, return a descriptive string that includes the **attempted URL** and the **error cause**. This allows the LLM to report the exact failure point to the user.
    ```typescript
    } catch (err: any) {
      return { content: [{ type: "text", text: `Error: ${err.message} [URL: ${ollamaUrl}]` }], isError: true };
    }
    ```

---

## **4. Verification Checklist**
- [ ] `Tool.from_schema` used in `agent.py`?
- [ ] Env vars added to `config.py`?
- [ ] `pnpm run build` executed in orchestrator?
- [ ] MCP logs show the correct number of tools discovered?
