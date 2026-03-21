"""PydanticAI Agent — wires LLM, MCP tools, and skill injection.

Creates the CogniBot agent with:
- System prompt compiled from SOUL.md + skill index
- Native Python tools (load_skill_context)
- MCP-discovered tools dynamically wrapped as PydanticAI tools
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic_ai import Agent, RunContext, Tool

from cognibot.config import CogniBotConfig
from cognibot.mcp_client import MCPBridge
from cognibot.skill_loader import compile_system_prompt, load_skill_content

logger = logging.getLogger(__name__)


# ── Dependency context injected into every tool call ─────────────────

class AgentDeps:
    """Runtime dependencies available to all agent tools."""

    def __init__(self, config: CogniBotConfig, mcp_bridge: MCPBridge) -> None:
        self.config = config
        self.mcp_bridge = mcp_bridge


# ── MCP tool wrapper factory ─────────────────────────────────────────

def _make_mcp_tool_fn(tool_name: str, description: str, input_schema: dict[str, Any]):
    """Create a PydanticAI Tool that proxies calls to the MCP adapter.

    Builds a proper Tool object with the tool's name, description from
    the MCP schema, and the JSON schema for parameter validation.
    """

    async def mcp_tool_proxy(ctx: RunContext[AgentDeps], **kwargs: Any) -> str:
        result = await ctx.deps.mcp_bridge.call_tool(tool_name, kwargs)
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

    return Tool(
        mcp_tool_proxy,
        takes_ctx=True,
        name=tool_name,
        description=description,
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
        try:
            content = load_skill_content(skill_id, ctx.deps.config.skills_dir)
            logger.info("Loaded skill context: %s (%d chars)", skill_id, len(content))
            return content
        except FileNotFoundError as e:
            return str(e)

    logger.info(
        "Agent created — %d MCP tools + 1 native tool (load_skill_context)",
        len(mcp_tools),
    )

    return agent
