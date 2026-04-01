"""
Builds the agent system prompt at runtime from the existing skill file and brand context.
The source files remain the single source of truth — nothing is duplicated here.
"""
from pathlib import Path


def build_system_prompt(project_root: Path) -> str:
    skill_file = project_root / ".claude" / "commands" / "repurpose-lead-magnet.md"
    brand_file = project_root / "brand" / "abhay-brand-context.md"

    if not skill_file.exists():
        raise FileNotFoundError(
            f"Skill file not found: {skill_file}\n"
            "Ensure .claude/commands/repurpose-lead-magnet.md exists."
        )

    parts = [skill_file.read_text(encoding="utf-8")]

    if brand_file.exists():
        parts.append("\n\n---\n\n## Brand Context\n\n")
        parts.append(brand_file.read_text(encoding="utf-8"))
    else:
        import warnings
        warnings.warn(
            f"Brand context file not found: {brand_file}. "
            "Agent will run without brand guidelines. "
            "Ensure brand/abhay-brand-context.md exists in the project root.",
            stacklevel=2,
        )

    return "".join(parts)
