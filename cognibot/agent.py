"""PydanticAI Agent — wires LLM, MCP tools, and skill injection.

Creates the CogniBot agent with:
- System prompt compiled from SOUL.md + skill index
- Native Python tools (load_skill_context)
- MCP-discovered tools dynamically wrapped as PydanticAI tools
"""

from __future__ import annotations

import base64
import json
import logging
import subprocess
import time
import sys
from typing import Any

from pydantic_ai import Agent, RunContext, Tool

from cognibot.config import CogniBotConfig
from cognibot.mcp_client import MCPBridge
from cognibot.memory import DOMAINS, SemanticMemoryStore
from cognibot.skill_loader import compile_system_prompt, load_skill_content

class YieldInterrupt(Exception):
    """Raised when the LLM wants to yield context and execution to Mission Control."""
    def __init__(self, state: str, milestone_idx: int, next_action: str, target_node: str | None, session_context: dict[str, Any] | None = None):
        self.state = state
        self.milestone_idx = milestone_idx
        self.next_action = next_action
        self.target_node = target_node
        self.session_context = session_context or {}
        super().__init__(f"Yielding to Mission Control: {state}")

logger = logging.getLogger(__name__)

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.align import Align

# Create a default console for tool logging
# In a real app, we might pass this in from main.py via Deps
_console = Console(theme=None) # Will use default color if not set



# ── Dependency context injected into every tool call ─────────────────

class AgentDeps:
    """Runtime dependencies available to all agent tools."""

    def __init__(
        self,
        config: CogniBotConfig,
        mcp_bridge: MCPBridge,
        memory: SemanticMemoryStore | None = None,
        console: Console | None = None,
    ) -> None:
        self.config = config
        self.mcp_bridge = mcp_bridge
        self.memory = memory  # SemanticMemoryStore (None if not initialized)
        self.console = console or _console

        # Phase 3: Tool call log (populated by _make_mcp_tool_fn wrapper)
        self.tool_call_log: list[dict[str, Any]] = []
        
        # Task Planner Context
        self.active_task_plan: dict[str, Any] | None = None
        self.heavy_tool_count: int = 0

        # TUI Hooks (to be injected by the TUI app if running)
        self.tui_on_tool_start = None
        self.tui_on_tool_end = None

    def start_tool_ui(self, name: str, args: dict[str, Any]) -> Any:
        """Trigger TUI 'start' hook and return the widget."""
        if self.tui_on_tool_start:
            return self.tui_on_tool_start(name, args)
        return None

    def end_tool_ui(self, widget: Any, result: str, success: bool = True):
        """Trigger TUI 'end' hook with result preview."""
        if self.tui_on_tool_end and widget:
            self.tui_on_tool_end(widget, result, success)




# ── MCP tool wrapper factory ─────────────────────────────────────────

def _make_mcp_tool_fn(tool_name: str, description: str, input_schema: dict[str, Any]):
    """Create a PydanticAI Tool that proxies calls to the MCP adapter.

    Builds a proper Tool object with the tool's name, description from
    the MCP schema, and the JSON schema for parameter validation.
    """

    async def mcp_tool_proxy(ctx: RunContext[AgentDeps], **kwargs: Any) -> str:
        # Display the tool call to the right (CLI)
        arg_json = json.dumps(kwargs, indent=2)
        
        # Hard log to stderr bypassing TUI for debugging
        sys.stderr.write(f"\n[DEBUG] Tool called: {tool_name}\n[DEBUG] Args: {arg_json}\n")
        sys.stderr.flush()
        
        panel = Panel(
            Syntax(arg_json, "json", theme="monokai", background_color="default"),
            title=f"🛠️  [bold yellow]Tool Call: {tool_name}[/bold yellow]",
            border_style="yellow",
            expand=False,
        )
        ctx.deps.console.print(Align.right(panel))

        # Hardware Interception Rule (Task Planner)
        heavy_tools = {"ros2_action_goal", "ros2_cmd_vel_duration", "ros2_vla_query", "ros2_publish"}
        if tool_name in heavy_tools:
            if ctx.deps.active_task_plan is None:
                ctx.deps.heavy_tool_count += 1
                if ctx.deps.heavy_tool_count > 2:
                    error_msg = (
                        "ERROR: You have attempted too many complex or physical actions without a plan. "
                        "You must use `create_task_plan` to outline your milestones before proceeding further."
                    )
                    ctx.deps.console.print(Align.right("[bold red]🚨 BLOCKED: Task Plan Required[/bold red]"))
                    return error_msg

        # TUI Notification
        tui_widget = ctx.deps.start_tool_ui(tool_name, kwargs)

        t_start = time.monotonic()
        result = await ctx.deps.mcp_bridge.call_tool(tool_name, kwargs)
        latency_ms = (time.monotonic() - t_start) * 1000
        
        is_error = result.get("isError", False)
        if is_error:
            ctx.deps.console.print(Align.right(f"[bold red]❌ Tool Error: {tool_name}[/bold red]"))
        else:
            ctx.deps.console.print(Align.right(f"[bold green]✅ Tool Success: {tool_name}[/bold green]"))

        # Single-pass content processing: build LLM response, log preview, and TUI result
        parts_preview: list[str] = []
        parts_llm: list[str] = []
        _result_str = ""
        for block in result.get("content", []):
            if block.get("type") == "text":
                _text = block["text"]
                parts_preview.append(_text[:200])
                parts_llm.append(_text)
                _result_str += _text
            elif block.get("type") == "image":
                parts_llm.append(f"[Image captured: {block.get('mimeType', 'image/jpeg')}]")
                try:
                    img_data = block["data"]
                    img_bytes = base64.b64decode(img_data)
                    mime = block.get("mimeType", "image/jpeg")
                    ext = "png" if "png" in mime else "jpg"
                    fpath = f"/tmp/cognibot_{int(time.time())}.{ext}"
                    with open(fpath, "wb") as f:
                        f.write(img_bytes)
                    # Automatically open the image in the default viewer (feh)
                    try:
                        subprocess.Popen(
                            ["feh", fpath],
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True
                        )
                        _result_str += f"\n📷 IMAGE: {fpath} (Opened with feh)\n"
                    except Exception:
                        _result_str += f"\n📷 IMAGE: {fpath}\n"
                except Exception as img_err:
                    _result_str += f"\n(Image save failed: {img_err})\n"
        
        ctx.deps.tool_call_log.append({
            "tool": tool_name,
            "args": kwargs,
            "success": not is_error,
            "latency_ms": round(latency_ms, 1),
            "result_preview": "\n".join(parts_preview)[:400],
            "timestamp": time.time(),
        })

        # TUI Notification
        ctx.deps.end_tool_ui(tui_widget, _result_str[:200], not is_error)

        return "\n".join(parts_llm) if parts_llm else "(no output)"

    mcp_tool_proxy.__name__ = tool_name
    mcp_tool_proxy.__qualname__ = tool_name
    mcp_tool_proxy.__doc__ = description

    # Build the parameters schema dict from the MCP inputSchema.
    # PydanticAI's Tool accepts takes_ctx=True and a JSON schema for parameters.
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": input_schema.get("properties", {}),
    }
    if "required" in input_schema:
        parameters_schema["required"] = input_schema["required"]

    return Tool.from_schema(
        mcp_tool_proxy,
        name=tool_name,
        description=description,
        json_schema=parameters_schema,
        takes_ctx=True,
    )


# ── Agent factory ────────────────────────────────────────────────────

def create_agent(config: CogniBotConfig, mcp_bridge: MCPBridge) -> Agent[AgentDeps, str]:
    """Build and return the CogniBot PydanticAI agent.

    1. Compiles the system prompt from SOUL.md + skill index.
    2. Creates the Agent with the configured LLM model.
    3. Registers the native ``load_skill_context`` tool.
    4. Wraps each MCP-discovered tool as a PydanticAI Tool.
    """

    # ── 1. System prompt ─────────────────────────────────────────────
    system_prompt = compile_system_prompt(config.soul_path, config.skills_dir)
    logger.info("System prompt compiled (%d chars)", len(system_prompt))

    # ── 2. Build MCP tool wrappers ───────────────────────────────────
    mcp_tools = mcp_bridge.get_tools()
    tool_objects = [
        _make_mcp_tool_fn(t.name, t.description, t.input_schema)
        for t in mcp_tools
    ]
    logger.info(
        "Wrapping %d MCP tools: %s",
        len(tool_objects),
        ", ".join(t.name for t in mcp_tools),
    )

    # ── 3. Create agent with tools ───────────────────────────────────
    model_to_use = config.llm_model
    
    # If using NVIDIA NIM, wrap it in OpenAIChatModel with the NVIDIA endpoint
    if config.llm_provider == "nvidia":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        
        nvidia_provider = OpenAIProvider(
            base_url='https://integrate.api.nvidia.com/v1',
            api_key=config.nvidia_api_key
        )
        model_to_use = OpenAIChatModel(config.llm_model, provider=nvidia_provider)

    agent: Agent[AgentDeps, str] = Agent(
        model=model_to_use,
        system_prompt=system_prompt,
        deps_type=AgentDeps,
        tools=tool_objects,
        retries=2,
    )

    # ── 4. Native tools ──────────────────────────────────────────────

    @agent.tool
    async def load_skill_context(ctx: RunContext[AgentDeps], skill_id: str) -> str:
        """Load the full instruction document for a skill by its ID.

        Use this when a task matches one of the skills listed in the
        Available Skills section of your system prompt. The full text
        will be returned so you can follow the skill's instructions.
        """
        ctx.deps.console.print(Align.right(f"🛠️  [bold cyan]Loading Skill: {skill_id}[/bold cyan]"))
        tui_widget = ctx.deps.start_tool_ui("load_skill_context", {"skill_id": skill_id})
        try:
            content = load_skill_content(skill_id, ctx.deps.config.skills_dir)
            ctx.deps.console.print(Align.right(f"[bold green]✅ Skill Loaded: {skill_id}[/bold green]"))
            ctx.deps.end_tool_ui(tui_widget, content[:200], success=True)
            return content
        except Exception as e:
            ctx.deps.console.print(Align.right(f"[bold red]❌ Skill Load Failed: {skill_id}[/bold red]"))
            ctx.deps.end_tool_ui(tui_widget, str(e), success=False)
            return str(e)

    @agent.tool
    async def create_task_plan(
        ctx: RunContext[AgentDeps],
        goal: str,
        milestones: list[str],
        required_nodes: list[str]
    ) -> str:
        """MANDATORY FIRST STEP for any complex, multi-step physical command.
        
        Deconstructs the human's command into discrete, verifiable robotic milestones before acting.
        Call this immediately when the user asks for a complex action or routine.
        If you call more than 2 heavy/physical tools without planning first, you will be blocked.
        
        Args:
            goal: The overarching objective (e.g., 'Locate missing blue bottle').
            milestones: Array of 3-5 specific steps (e.g., ['Query memory for lab coordinates', 'Navigate to lab']).
            required_nodes: Name of ROS2 nodes that must be active (e.g., ['nav2', 'vla_server']).
        """
        ctx.deps.active_task_plan = {
            "goal": goal,
            "milestones": milestones,
            "required_nodes": required_nodes,
            "session_context": {}
        }
        ctx.deps.heavy_tool_count = 0  # Reset counter once plan is active
        tui_widget = ctx.deps.start_tool_ui("create_task_plan", {"goal": goal})
        
        # Write to physical file for Mission Control access
        plan_path = "/tmp/cognibot_task_plan.json"
        try:
            with open(plan_path, "w") as f:
                json.dump(ctx.deps.active_task_plan, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write task plan to disk: {e}")
        
        ctx.deps.console.print(Align.right(f"📋 [bold yellow]Task Plan Saved to Disk:[/bold yellow] {goal}"))
        for i, m in enumerate(milestones, 1):
            ctx.deps.console.print(Align.right(f"   [dim]{i}. {m}[/dim]"))
            
        res = f"Task Plan '{goal}' successfully registered and saved. Proceed with your first milestone."
        ctx.deps.end_tool_ui(tui_widget, res, success=True)
        return res

    @agent.tool
    async def yield_status(
        ctx: RunContext[AgentDeps],
        state: str,
        current_milestone_index: int,
        next_action: str,
        target_node: str | None = None,
        session_context: dict[str, Any] | None = None
    ) -> str:
        """Call this to pause your cognitive loop, clear context, or wait on hardware.
        
        MUST be called after completing a milestone, running into a task that takes time 
        (like starting Nav2 or exploration), or reaching an error you cannot solve.
        
        Args:
            state: One of ["MILESTONE_COMPLETE", "WAITING_ON_NODE", "BLOCKED", "REQUIRE_HUMAN"].
            current_milestone_index: Where you are in the JSON task plan array (1-indexed).
            next_action: A brief instruction to YOURSELF for when Mission Control wakes you back up.
            target_node: If WAITING_ON_NODE, the ROS2 node name you are waiting on.
            session_context: Optional dictionary to store state across yields (e.g. {"iteration": 2}). 
                This survives context wipes and will be re-injected on wakeup.
        """
        ctx.deps.console.print(Align.right(f"⏸️  [bold yellow]Yielding to Mission Control...[/bold yellow]"))
        tui_widget = ctx.deps.start_tool_ui("yield_status", {"state": state, "milestone": current_milestone_index})
        ctx.deps.end_tool_ui(tui_widget, f"Yielding with state {state}", success=True)
        raise YieldInterrupt(state, current_milestone_index, next_action, target_node, session_context)

    # ── 5. Semantic Memory tools ──────────────────────────────────────
    _domains_str = ", ".join(DOMAINS.keys())
    _domains_detail = "\n".join(f"  - `{k}`: {v}" for k, v in DOMAINS.items())

    @agent.tool
    async def query_semantic_memory(
        ctx: RunContext[AgentDeps],
        domain: str,
        query: str = "memory",
        n_results: int = 5,
    ) -> str:
        """Search the robot's persistent semantic memory for relevant context.

        Use this BEFORE navigating to a location, when recalling operator
        preferences, when checking environment conditions, or when looking up
        custom policies. Always query memory first on any spatial or behavioral task.

        Args:
            domain: Memory category — one of: spatial, behavioral, env_context, policy
              - `spatial`: Waypoints, known obstacles, alternate routes, building layouts.
              - `behavioral`: Past human interactions, successful/failed commands, operator preferences.
              - `env_context`: Time-of-day lighting, crowd densities, scheduled maintenance windows.
              - `policy`: Custom rules like 'never drive near wet floor' or 'prioritize charging'.
            query: Natural language search query (e.g. 'charging dock location'). To list all entries or browse, pass a general term like 'memory'. NEVER pass an empty string or null, as it will cause an error in the embedding model.
            n_results: Number of results to return (default 5, max 20)
        """
        if ctx.deps.memory is None:
            return "Semantic memory is not initialized."
        
        ctx.deps.console.print(Align.right(f"🧠 [bold magenta]Memory Query [{domain}]: {query[:60]}[/bold magenta]"))
        tui_widget = ctx.deps.start_tool_ui("query_semantic_memory", {"domain": domain, "query": query})
        
        try:
            results = await ctx.deps.memory.query(domain, query, n_results=min(n_results, 20))
            if not results:
                msg = f"No memories found in domain '{domain}' for query: {query}"
                ctx.deps.end_tool_ui(tui_widget, msg, success=True)
                return msg
                
            lines = [f"Semantic memory results from domain '{domain}' ({len(results)} found):"]
            for i, r in enumerate(results, 1):
                lines.append(f"  {i}. {r.to_summary()}")
            
            ctx.deps.console.print(Align.right(f"[bold green]✅ Memory: {len(results)} results[/bold green]"))
            res_str = "\n".join(lines)
            ctx.deps.end_tool_ui(tui_widget, res_str[:200], success=True)
            return res_str
        except Exception as exc:
            ctx.deps.console.print(Align.right(f"[bold red]❌ Memory query failed[/bold red]"))
            ctx.deps.end_tool_ui(tui_widget, str(exc), success=False)
            return f"Memory query failed: {exc}"

    @agent.tool
    async def store_memory(
        ctx: RunContext[AgentDeps],
        domain: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store a new entry in the robot's persistent semantic memory.

        Use this to remember important spatial information, operator preferences,
        environmental patterns, or custom policies for future sessions.
        Stored memories persist across restarts and are retrieved via query_semantic_memory.

        Args:
            domain: Memory category — one of: spatial, behavioral, env_context, policy
              - `spatial`: Waypoints, known obstacles, alternate routes, building layouts.
              - `behavioral`: Past human interactions, successful/failed commands, operator preferences.
              - `env_context`: Time-of-day lighting, crowd densities, scheduled maintenance windows.
              - `policy`: Custom rules like 'never drive near wet floor' or 'prioritize charging'.
            content: The text to remember (be descriptive and specific)
            metadata: Optional key-value tags (e.g. {"label": "charging_dock", "x": 1.5})
        """
        if ctx.deps.memory is None:
            return "Semantic memory is not initialized."
        
        ctx.deps.console.print(Align.right(f"💾 [bold magenta]Storing Memory [{domain}][/bold magenta]"))
        tui_widget = ctx.deps.start_tool_ui("store_memory", {"domain": domain, "content": content[:50]})

        try:
            doc_id = await ctx.deps.memory.store(domain, content, metadata or {})
            ctx.deps.console.print(Align.right(f"[bold green]✅ Memory stored: {doc_id[:8]}...[/bold green]"))
            res = f"Memory stored successfully. ID: {doc_id}"
            ctx.deps.end_tool_ui(tui_widget, res, success=True)
            return res
        except Exception as exc:
            ctx.deps.console.print(Align.right(f"[bold red]❌ Memory store failed[/bold red]"))
            ctx.deps.end_tool_ui(tui_widget, str(exc), success=False)
            return f"Failed to store memory: {exc}"

    @agent.tool
    async def delete_memory(
        ctx: RunContext[AgentDeps],
        domain: str,
        doc_id: str,
    ) -> str:
        """Delete a specific entry from semantic memory.

        Use this when a fact has become outdated or incorrect (e.g. a piece of
        furniture has moved, or a policy is no longer in effect).
        CRITICAL: You MUST NOT invent or ask the human operator for a doc_id. 
        You MUST find the exact doc_id autonomously by first calling query_semantic_memory 
        and reading the results before calling delete_memory.

        Args:
            domain: Memory category — one of: spatial, behavioral, env_context, policy
            doc_id: The unique ID of the memory entry to remove.
        """
        if ctx.deps.memory is None:
            return "Semantic memory is not initialized."
            
        ctx.deps.console.print(Align.right(f"🗑️ [bold red]Deleting Memory [{domain}]: {doc_id[:8]}[/bold red]"))
        tui_widget = ctx.deps.start_tool_ui("delete_memory", {"domain": domain, "doc_id": doc_id})
        
        try:
            success = await ctx.deps.memory.delete(domain, doc_id)
            if success:
                ctx.deps.console.print(Align.right(f"[bold green]✅ Memory deleted[/bold green]"))
                ctx.deps.end_tool_ui(tui_widget, "Success", success=True)
                return f"Memory {doc_id} deleted successfully from domain '{domain}'."
            else:
                ctx.deps.console.print(Align.right(f"[bold yellow]⚠ Delete failed (not found)[/bold yellow]"))
                ctx.deps.end_tool_ui(tui_widget, "Not found", success=False)
                return f"Could not find memory {doc_id} in domain '{domain}'."
        except Exception as exc:
            ctx.deps.console.print(Align.right(f"[bold red]❌ Memory delete failed[/bold red]"))
            ctx.deps.end_tool_ui(tui_widget, str(exc), success=False)
            return f"Failed to delete memory: {exc}"

    # ── 6. Memory-biased navigation planner ──────────────────────────

    @agent.tool
    async def plan_memory_route(
        ctx: RunContext[AgentDeps],
        destination_label: str,
        context_hint: str = "",
    ) -> str:
        """Query spatial and behavioral memory for a preferred route to a destination.

        Call this BEFORE ros2_action_goal when navigating to a named location.
        Returns waypoints, known hazards, preferred paths, and behavioral context
        from past navigation sessions.

        If waypoints with x/y/theta are found, use /navigate_through_poses (Nav2
        waypoint follower) to inject the full path. Otherwise fall back to
        /navigate_to_pose with the final destination coordinates.

        Args:
            destination_label: Human-readable destination (e.g. 'charging dock', 'Door A')
            context_hint: Additional context to narrow the search (e.g. 'weekend morning')
        """
        if ctx.deps.memory is None:
            return "Semantic memory is not initialized. Use direct Nav2 navigation."

        ctx.deps.console.print(
            Align.right(f"🗺️ [bold magenta]Planning route to: {destination_label}[/bold magenta]")
        )
        tui_widget = ctx.deps.start_tool_ui("plan_memory_route", {"destination": destination_label})

        try:
            search_text = f"route to {destination_label} {context_hint}".strip()
            spatial = await ctx.deps.memory.query("spatial", search_text, n_results=5)
            behavioral = await ctx.deps.memory.query("behavioral", search_text, n_results=3)
            env = await ctx.deps.memory.query("env_context", search_text, n_results=2)
            policy = await ctx.deps.memory.query("policy", search_text, n_results=2)

            sections: list[str] = [f"=== Route Plan: '{destination_label}' ==="]

            if spatial:
                sections.append("--- Spatial Knowledge (waypoints / obstacles) ---")
                for r in spatial:
                    sections.append(f"  • {r.to_summary()}")
            else:
                sections.append("No spatial memories found for this destination. Use default Nav2 goal.")

            if behavioral:
                sections.append("--- Behavioral History ---")
                for r in behavioral:
                    sections.append(f"  • {r.to_summary()}")

            if env:
                sections.append("--- Environmental Context ---")
                for r in env:
                    sections.append(f"  • {r.to_summary()}")

            if policy:
                sections.append("--- Active Policies ---")
                for r in policy:
                    sections.append(f"  • {r.to_summary()}")

            sections.append(
                "\nInstruction: If waypoints with x/y/theta are listed above, "
                "use /navigate_through_poses. Otherwise use /navigate_to_pose "
                "with the final destination coordinates."
            )

            ctx.deps.console.print(
                Align.right(f"[bold green]✅ Route plan ready ({len(spatial)} spatial memories)[/bold green]")
            )
            res_str = "\n".join(sections)
            ctx.deps.end_tool_ui(tui_widget, f"Plan ready: {len(spatial)} waypoints", success=True)
            return res_str
        except Exception as exc:
            ctx.deps.console.print(Align.right(f"[bold red]❌ Route planning failed[/bold red]"))
            ctx.deps.end_tool_ui(tui_widget, str(exc), success=False)
            return f"Route planning failed: {exc}. Fall back to direct navigation."


    logger.info(
        "Agent created — %d MCP tools + 7 native tools "
        "(load_skill_context, create_task_plan, yield_status, "
        "query_semantic_memory, store_memory, delete_memory, plan_memory_route)",
        len(mcp_tools),
    )

    return agent
