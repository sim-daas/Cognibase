"""CogniBot CLI entry point.

Starts the orchestrator: loads config, connects the MCP bridge,
creates the PydanticAI agent, and runs an interactive REPL.

Usage:
    python -m cognibot.main              # Full interactive mode
    python -m cognibot.main --dry-run    # Validate config + skills only

Message History:
    The REPL maintains a rolling message history for the current session.
    This gives the agent multi-turn conversational memory within one run.
    History is capped at MAX_HISTORY_TURNS turn-pairs to avoid token exhaustion.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Any

from pydantic_ai.messages import ModelMessage

from cognibot.config import CogniBotConfig, load_config
from cognibot.mcp_client import MCPBridge
from cognibot.agent import AgentDeps, create_agent
from cognibot.skill_loader import compile_system_prompt, scan_skills

# ── Logging ──────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cognibot")

# ── Message History Config ────────────────────────────────────────────
# Keep this many user/assistant turn-pairs in the rolling history.
# Each Nav2 action can generate many internal messages (tool calls + results),
# so keep this conservative to avoid token overflow.
MAX_HISTORY_TURNS = 10


# ── Dry-run mode ─────────────────────────────────────────────────────

def dry_run(config: CogniBotConfig) -> None:
    """Validate config, scan skills, print system prompt, and exit."""
    print("\n═══ CogniBot Dry Run ═══\n")

    print(f"LLM Provider : {config.llm_provider}")
    print(f"LLM Model    : {config.llm_model}")
    print(f"Skills Dir   : {config.skills_dir}")
    print(f"SOUL Path    : {config.soul_path}")
    print(f"MCP Script   : {config.mcp_server_script}")
    print(f"MCP Script exists: {config.mcp_server_script.exists()}")

    print("\n── Skills ──")
    skills = scan_skills(config.skills_dir)
    if skills:
        for s in skills:
            print(f"  • {s.skill_id}: {s.description}")
    else:
        print("  (no skills found)")

    print("\n── System Prompt ──")
    prompt = compile_system_prompt(config.soul_path, config.skills_dir)
    # Print first 2000 chars to avoid flooding
    if len(prompt) > 2000:
        print(prompt[:2000])
        print(f"\n  ... ({len(prompt) - 2000} more chars)")
    else:
        print(prompt)

    print("\n═══ Dry run complete ═══")


# ── Message history helpers ───────────────────────────────────────────

def _trim_history(history: list[ModelMessage]) -> list[ModelMessage]:
    """Keep the most recent MAX_HISTORY_TURNS exchange pairs.

    PydanticAI message history contains interleaved user/model/tool
    messages. We trim by counting from the end, keeping messages that
    belong to the most recent N turns. A simple heuristic: count
    ModelRequest objects as turn boundaries.
    """
    from pydantic_ai.messages import ModelRequest

    # Walk backwards counting user requests (turn boundaries)
    turn_count = 0
    cut_index = len(history)
    for i in range(len(history) - 1, -1, -1):
        if isinstance(history[i], ModelRequest):
            turn_count += 1
            if turn_count > MAX_HISTORY_TURNS:
                cut_index = i + 1
                break
    return history[cut_index:]


# ── Interactive REPL ─────────────────────────────────────────────────

async def run_interactive(config: CogniBotConfig) -> None:
    """Main interactive loop: connect MCP, create agent, REPL."""
    bridge = MCPBridge(config)

    print("\n╔══════════════════════════════════════╗")
    print("║       CogniBot — Agentic Robot       ║")
    print("╚══════════════════════════════════════╝\n")

    # ── Connect MCP adapter ──────────────────────────────────────────
    print("Connecting to MCP adapter...")
    try:
        await bridge.connect()
    except Exception as e:
        logger.error("Failed to connect MCP adapter: %s", e)
        print(f"\n✗ MCP adapter connection failed: {e}")
        print("  Make sure the MCP adapter is built:")
        print(f"    cd {config.mcp_server_script.parent.parent.parent}")
        print("    pnpm install && pnpm build")
        print("\n  And rosbridge_server is running on ws://localhost:9090")
        return

    tools = bridge.get_tools()
    print(f"✓ MCP adapter connected — {len(tools)} tools available")
    for t in tools:
        print(f"  • {t.name}")

    # ── Create agent ─────────────────────────────────────────────────
    print("\nInitializing agent...")
    try:
        agent = create_agent(config, bridge)
    except Exception as e:
        logger.error("Failed to create agent: %s", e)
        await bridge.disconnect()
        return

    deps = AgentDeps(config=config, mcp_bridge=bridge)
    print(f"✓ Agent ready (model: {config.llm_model})")
    print(f"  Session memory: last {MAX_HISTORY_TURNS} turns retained")
    print("\nType your commands (Ctrl+C or 'exit' to quit):\n")

    # ── Message history for this session ─────────────────────────────
    message_history: list[ModelMessage] = []

    # ── REPL ─────────────────────────────────────────────────────────
    try:
        while True:
            try:
                user_input = input("You > ").strip()
            except EOFError:
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                break
            if user_input.lower() in ("history", "/history"):
                print(f"  [History: {len(message_history)} messages in current session]")
                continue
            if user_input.lower() in ("clear", "/clear"):
                message_history = []
                print("  [History cleared]")
                continue

            try:
                result = await agent.run(
                    user_input,
                    deps=deps,
                    message_history=message_history if message_history else None,
                )
                # Append new messages to history and trim to limit
                message_history.extend(result.new_messages())
                message_history = _trim_history(message_history)

                print(f"\nCogniBot > {result.output}\n")
                logger.debug("History size: %d messages", len(message_history))

            except Exception as e:
                logger.error("Agent error: %s", e, exc_info=True)
                print(f"\n✗ Error: {e}\n")

    except KeyboardInterrupt:
        print("\n\nShutting down...")
    finally:
        await bridge.disconnect()
        print("Goodbye.")


# ── Entry point ──────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="CogniBot — Agentic Robotics Orchestrator"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and skills without connecting to MCP or LLM",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to environment config file (default: auto-detect)",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    if args.dry_run:
        dry_run(config)
        sys.exit(0)

    asyncio.run(run_interactive(config))


if __name__ == "__main__":
    main()
