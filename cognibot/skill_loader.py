"""Dynamic Skill Loader — Boot scraper and on-demand context injection.

Scans the skills directory for ``.md`` files, extracts SKILL_ID and
DESCRIPTION metadata from headers, builds a system prompt from
SOUL.md + a skill index, and provides on-demand full-text loading.

Skill scanning happens once at import/startup and results are cached.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillMeta:
    """Metadata extracted from a skill document header."""

    skill_id: str
    description: str
    file_path: Path


# Extract SKILL_ID and DESCRIPTION, ignoring markdown bold tags and escaped underscores
_HEADER_RE = re.compile(
    r"SKILL\\?_ID:\s*([a-zA-Z0-9_\-\\]+).*?DESCRIPTION:\s*(.+?)(?:\*\*\s*$|$)",
    re.IGNORECASE | re.DOTALL,
)

# ── Module-level skill index cache ───────────────────────────────────
# Keyed by the resolved skills directory path to support multiple dirs.
_skill_cache: dict[str, list[SkillMeta]] = {}


def scan_skills(skills_dir: str | Path) -> list[SkillMeta]:
    """Scan a directory for skill ``.md`` files and extract metadata.

    Results are cached per directory path — subsequent calls with the
    same directory return instantly without re-reading the filesystem.
    ``SOUL.md`` is excluded (it is the system identity, not a skill).
    """
    resolved = str(Path(skills_dir).resolve())
    if resolved in _skill_cache:
        return _skill_cache[resolved]

    skills_dir = Path(resolved)
    results: list[SkillMeta] = []

    if not skills_dir.is_dir():
        _skill_cache[resolved] = results
        return results

    for md_file in sorted(skills_dir.rglob("*.md")):
        if md_file.name.upper() == "SOUL.MD":
            continue

        try:
            with md_file.open("r", encoding="utf-8") as f:
                content = f.read()

            match = _HEADER_RE.search(content)
            if match:
                results.append(
                    SkillMeta(
                        skill_id=match.group(1).strip(),
                        description=match.group(2).strip(),
                        file_path=md_file,
                    )
                )
        except OSError:
            continue

    _skill_cache[resolved] = results
    return results


def invalidate_skill_cache(skills_dir: str | Path | None = None) -> None:
    """Clear the skill cache.

    Call this if skill files are added/modified at runtime.
    Pass *skills_dir* to clear only that directory, or ``None`` to clear all.
    """
    global _skill_cache
    if skills_dir is None:
        _skill_cache = {}
    else:
        _skill_cache.pop(str(Path(skills_dir).resolve()), None)


def build_skill_index(skills: list[SkillMeta]) -> str:
    """Format a numbered skill index for injection into the system prompt."""
    if not skills:
        return "(No skills loaded.)"

    lines = ["## Available Skills", ""]
    for i, s in enumerate(skills, 1):
        lines.append(f"{i}. **{s.skill_id}** — {s.description}")
    lines.append("")
    lines.append(
        'To load the full instructions for a skill, call the tool `load_skill_context` '
        "with the skill_id above."
    )
    return "\n".join(lines)


def compile_system_prompt(soul_path: str | Path, skills_dir: str | Path) -> str:
    """Build the complete system prompt from SOUL.md + skill index.

    Returns the concatenated string ready for PydanticAI's system prompt.
    """
    soul_path = Path(soul_path)
    soul_text = ""
    if soul_path.is_file():
        soul_text = soul_path.read_text(encoding="utf-8").strip()

    skills = scan_skills(skills_dir)
    index = build_skill_index(skills)

    parts = []
    if soul_text:
        parts.append(soul_text)
    parts.append(index)

    return "\n\n---\n\n".join(parts)


def load_skill_content(skill_id: str, skills_dir: str | Path) -> str:
    """Load the full text of a skill document by its ID.

    Uses the cached skill index from ``scan_skills`` — no re-scan.
    Raises ``FileNotFoundError`` if the skill is not found.
    """
    skills = scan_skills(skills_dir)  # returns from cache
    for skill in skills:
        if skill.skill_id == skill_id:
            return skill.file_path.read_text(encoding="utf-8")

    available = ", ".join(s.skill_id for s in skills) or "(none)"
    raise FileNotFoundError(
        f"Skill '{skill_id}' not found. Available skills: {available}"
    )
