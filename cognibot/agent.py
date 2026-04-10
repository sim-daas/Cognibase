"""PydanticAI Agent — wires LLM, MCP tools, and skill injection.

Creates the CogniBot agent with:
- System prompt compiled from SOUL.md + skill index
- Native Python tools (load_skill_context)
- MCP-discovered tools dynamically wrapped as PydanticAI tools
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from pydantic_ai import Agent, RunContext, Tool

from cognibot.config import CogniBotConfig
from cognibot.mcp_client import MCPBridge
from cognibot.memory import DOMAINS, SemanticMemoryStore
from cognibot.skill_loader import compile_system_prompt, load_skill_content

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
        panel = Panel(
            Syntax(arg_json, "json", theme="monokai", background_color="default"),
            title=f"🛠️  [bold yellow]Tool Call: {tool_name}[/bold yellow]",
            border_style="yellow",
            expand=False,
        )
        ctx.deps.console.print(Align.right(panel))

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

        # Phase 3: append to tool call log
        parts_preview: list[str] = []
        _result_str = ""
        for block in result.get("content", []):
            if block.get("type") == "text":
                _text = block["text"]
                parts_preview.append(_text[:200])
                _result_str += _text
        
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

        # Stringify content blocks for the LLM
        parts: list[str] = []
        for block in result.get("content", []):
            if block.get("type") == "text":
                parts.append(block["text"])
            elif block.get("type") == "image":
                parts.append(f"[Image captured: {block.get('mimeType', 'image/jpeg')}]")
        return "\n".join(parts) if parts else "(no output)"

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
    agent: Agent[AgentDeps, str] = Agent(
        model=config.llm_model,
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

    # ── 5. Semantic Memory tools ──────────────────────────────────────
    _domains_str = ", ".join(DOMAINS.keys())
    _domains_detail = "\n".join(f"  - `{k}`: {v}" for k, v in DOMAINS.items())

    @agent.tool
    async def query_semantic_memory(
        ctx: RunContext[AgentDeps],
        domain: str,
        query: str,
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
            query: Natural language search query (e.g. 'charging dock location')
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
        "Agent created — %d MCP tools + 4 native tools "
        "(load_skill_context, query_semantic_memory, store_memory, plan_memory_route)",
        len(mcp_tools),
    )

    return agent
