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
logging.getLogger("httpx").setLevel(logging.DEBUG) 
import sys
from typing import Any

from pydantic_ai.messages import ModelMessage

from cognibot.config import CogniBotConfig, load_config
from cognibot.mcp_client import MCPBridge
from cognibot.agent import AgentDeps, create_agent
from cognibot.memory import SemanticMemoryStore
from cognibot.skill_loader import compile_system_prompt, scan_skills
from cognibot.tui import CogniBotTUI


# ── Logging ──────────────────────────────────────────────────────────
# Suppress noisy library logs (httpx, openai, etc.)
logging.basicConfig(level=logging.WARNING)
for logger_name in ["httpx", "openai", "httpcore", "mcp"]:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

logger = logging.getLogger("cognibot")
logger.setLevel(logging.INFO)

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.markdown import Markdown
from rich.text import Text
from rich.align import Align
from rich.theme import Theme

custom_theme = Theme({
    "info": "dim cyan",
    "warning": "magenta",
    "danger": "bold red",
    "user": "bold green",
    "bot": "bold blue",
    "think": "dim italic grey50",
    "tool": "bold yellow",
})

console = Console(theme=custom_theme)


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

async def run_interactive(config: CogniBotConfig, theme: str = None) -> None:
    """Main entry point for interactive mode: connect MCP and launch TUI."""
    bridge = MCPBridge(config)

    console.print("\n[bold cyan]Starting CogniBot TUI...[/bold cyan]")

    # ── Initialize Semantic Memory ────────────────────────────────────
    memory = SemanticMemoryStore(
        db_path=config.memory_db_path,
        ollama_url=config.memory_embedding_url,
    )
    try:
        await memory.initialize()
        stats = await memory.stats()
        total = sum(stats.values())
        console.print(
            f"[bold green]✅ Semantic Memory ready[/bold green] "
            f"— {total} memories across {len(stats)} domains "
            f"(db: {config.memory_db_path}, embed: {config.memory_embedding_url})"
        )
    except Exception as e:
        logger.warning("Semantic memory init failed: %s", e)
        console.print(f"[warning]⚠ Semantic memory unavailable:[/warning] {e}")
        memory = None  # type: ignore[assignment]

    # ── Connect MCP adapter ───────────────────────────────────────────
    try:
        await bridge.connect()
    except Exception as e:
        logger.error("Failed to connect MCP adapter: %s", e)
        console.print(f"\n[danger]✗ MCP adapter connection failed:[/danger] {e}")
        return

    # ── Create agent ──────────────────────────────────────────────────
    try:
        agent = create_agent(config, bridge)
    except Exception as e:
        logger.error("Failed to create agent: %s", e)
        await bridge.disconnect()
        return

    deps = AgentDeps(config=config, mcp_bridge=bridge, memory=memory, console=console)

    from cognibot.review import start_review_api
    review_task = asyncio.create_task(start_review_api(config.skills_dir))

    # ── Launch TUI ────────────────────────────────────────────────────
    app = CogniBotTUI(agent=agent, deps=deps)
    if theme:
        app.theme = theme
    try:
        await app.run_async()
    except Exception as e:
        logger.error("TUI Error: %s", e)
    finally:
        await bridge.disconnect()



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
    parser.add_argument(
        "--theme",
        type=str,
        default=None,
        help="Textual theme to use for the TUI (e.g., textual-dark, dracula, etc.)",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    if args.dry_run:
        dry_run(config)
        sys.exit(0)

    asyncio.run(run_interactive(config, args.theme))


if __name__ == "__main__":
    main()
