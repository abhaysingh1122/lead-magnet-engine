"""
Configuration loader for the Lead Magnet Agent.
Reads .env from the project root and validates required API keys.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

_REQUIRED_KEYS = ["ANTHROPIC_API_KEY", "NOTION_API_KEY", "NOTION_PARENT_PAGE_ID", "GEMINI_API_KEY"]


def load_and_validate_env(project_root: Path) -> None:
    """Load .env from project_root and raise EnvironmentError if any required keys are missing."""
    load_dotenv(project_root / ".env")
    missing = [k for k in _REQUIRED_KEYS if not os.getenv(k)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"Copy .env.example to .env and fill in the values."
        )
