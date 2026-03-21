"""MCP Client — manages the AgenticROS MCP adapter subprocess.

Spawns the Node.js MCP server via stdio, discovers available tools,
and provides a typed interface for tool invocation.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from cognibot.config import CogniBotConfig

logger = logging.getLogger(__name__)


@dataclass
class MCPToolDef:
    """Schema of a single MCP tool discovered from the adapter."""

    name: str
    description: str
    input_schema: dict[str, Any]


class MCPBridge:
    """Lifecycle manager for the AgenticROS MCP adapter subprocess.

    Usage::

        bridge = MCPBridge(config)
        await bridge.connect()
        tools = bridge.get_tools()
        result = await bridge.call_tool("ros2_list_topics", {})
        await bridge.disconnect()
    """

    def __init__(self, config: CogniBotConfig) -> None:
        self._config = config
        self._exit_stack = AsyncExitStack()
        self._session: ClientSession | None = None
        self._tools: list[MCPToolDef] = []

    # ── Connection lifecycle ─────────────────────────────────────────

    async def connect(self) -> None:
        """Spawn the MCP adapter and perform tool discovery."""
        if self._session is not None:
            logger.warning("MCPBridge already connected")
            return

        server_params = StdioServerParameters(
            command=self._config.mcp_server_command,
            args=self._config.mcp_server_args,
            env={
                **self._config.mcp_env,
                # Ensure Node.js stderr doesn't pollute MCP JSON-RPC
                "NODE_NO_WARNINGS": "1",
            },
        )

        logger.info(
            "Starting MCP adapter: %s %s",
            server_params.command,
            " ".join(server_params.args),
        )

        # Enter the stdio client context (spawns subprocess)
        read_stream, write_stream = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )

        # Create and initialise the MCP session
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await self._session.initialize()

        # Discover tools
        response = await self._session.list_tools()
        self._tools = [
            MCPToolDef(
                name=t.name,
                description=t.description or "",
                input_schema=t.inputSchema if isinstance(t.inputSchema, dict) else {},
            )
            for t in response.tools
        ]

        logger.info(
            "MCP adapter connected — %d tools discovered: %s",
            len(self._tools),
            ", ".join(t.name for t in self._tools),
        )

    async def disconnect(self) -> None:
        """Shut down the MCP adapter subprocess."""
        await self._exit_stack.aclose()
        self._session = None
        self._tools = []
        logger.info("MCP adapter disconnected")

    # ── Tool interface ───────────────────────────────────────────────

    def get_tools(self) -> list[MCPToolDef]:
        """Return the list of discovered MCP tools."""
        return list(self._tools)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke an MCP tool and return the result.

        Returns a dict with ``content`` (list of content blocks) and
        optional ``isError`` flag.
        """
        if self._session is None:
            raise RuntimeError("MCPBridge is not connected. Call connect() first.")

        logger.debug("Calling MCP tool: %s(%s)", name, json.dumps(arguments, default=str)[:200])

        result = await self._session.call_tool(name, arguments)

        # Normalise content to a simple dict
        content_blocks: list[dict[str, Any]] = []
        for block in result.content:
            if hasattr(block, "text"):
                content_blocks.append({"type": "text", "text": block.text})
            elif hasattr(block, "data"):
                content_blocks.append({
                    "type": "image",
                    "data": block.data,
                    "mimeType": getattr(block, "mimeType", "image/jpeg"),
                })
            else:
                content_blocks.append({"type": "text", "text": str(block)})

        return {
            "content": content_blocks,
            "isError": getattr(result, "isError", False),
        }

    @property
    def is_connected(self) -> bool:
        return self._session is not None
