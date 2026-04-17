"""CogniBot runtime configuration.

Reads from environment variables (or a .env file) and provides typed
config for the orchestrator, LLM provider, and MCP adapter paths.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


# ── Defaults ─────────────────────────────────────────────────────────

_DEFAULT_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
_DEFAULT_SOUL_PATH = _DEFAULT_SKILLS_DIR / "SOUL.md"
_DEFAULT_MCP_SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "agenticros"
    / "packages"
    / "agenticros-claude-code"
    / "dist"
    / "index.js"
)


@dataclass(frozen=True)
class CogniBotConfig:
    """Immutable runtime configuration for CogniBot."""

    # ── LLM ──────────────────────────────────────────────────────────
    llm_provider: str = "gemini"
    llm_model: str = "google-gla:gemini-2.0-flash"
    nvidia_api_key: str | None = None

    # ── Paths ────────────────────────────────────────────────────────
    skills_dir: Path = _DEFAULT_SKILLS_DIR
    soul_path: Path = _DEFAULT_SOUL_PATH
    mcp_server_script: Path = _DEFAULT_MCP_SCRIPT
    agenticros_config_path: Path = Path("/app/config/agenticros.json")

    # ── Semantic Memory ───────────────────────────────────────────────
    memory_db_path: Path = Path("./memory_db")
    memory_embedding_url: str = "http://localhost:11434"  # Ollama base URL

    # ── MCP subprocess ───────────────────────────────────────────────
    mcp_server_command: str = "node"

    @property
    def mcp_server_args(self) -> list[str]:
        return [str(self.mcp_server_script)]

    @property
    def mcp_env(self) -> dict[str, str]:
        """Environment variables passed to the MCP adapter subprocess."""
        env: dict[str, str] = {}
        if self.agenticros_config_path.exists():
            env["AGENTICROS_CONFIG_PATH"] = str(self.agenticros_config_path)
        
        if self.nvidia_api_key:
            env["NVIDIA_API_KEY"] = self.nvidia_api_key

        ollama_base = os.getenv("OLLAMA_BASE_URL")
        if ollama_base:
            env["OLLAMA_BASE_URL"] = ollama_base
            
        return env


def load_config(env_file: str | Path | None = None) -> CogniBotConfig:
    """Load configuration from environment variables.

    If *env_file* is given (or ``COGNIBOT_CONFIG_PATH`` is set), the
    file is loaded first so its values appear as env vars.
    """
    env_path = env_file or os.getenv("COGNIBOT_CONFIG_PATH")
    if env_path:
        load_dotenv(env_path, override=True)

    def _path(key: str, default: Path) -> Path:
        val = os.getenv(key)
        return Path(val) if val else default

    provider = os.getenv("COGNIBOT_LLM_PROVIDER", "gemini").lower()

    # Map provider to PydanticAI model string
    model_defaults = {
        "gemini": "google-gla:gemini-2.0-flash",
        "ollama": "ollama:llama3.2",
        "groq": "groq:llama-3.3-70b-versatile",
        "nvidia": "meta/llama-4-maverick-17b-128e-instruct",
    }
    model = os.getenv("COGNIBOT_LLM_MODEL", model_defaults.get(provider, model_defaults["gemini"]))

    return CogniBotConfig(
        llm_provider=provider,
        llm_model=model,
        nvidia_api_key=os.getenv("NVIDIA_API_KEY"),
        skills_dir=_path("COGNIBOT_SKILLS_DIR", _DEFAULT_SKILLS_DIR),
        soul_path=_path("COGNIBOT_SOUL_PATH", _DEFAULT_SOUL_PATH),
        mcp_server_script=_path("COGNIBOT_MCP_SERVER_SCRIPT", _DEFAULT_MCP_SCRIPT),
        agenticros_config_path=_path("AGENTICROS_CONFIG_PATH", Path("/app/config/agenticros.json")),
        memory_db_path=_path("COGNIBOT_MEMORY_DB_PATH", Path("./memory_db")),
        memory_embedding_url=os.getenv("COGNIBOT_MEMORY_EMBEDDING_URL", "http://localhost:11434"),
    )
