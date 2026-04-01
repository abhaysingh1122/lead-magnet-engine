"""
Lead Magnet Agent — public interface.

Embed in any Python environment that can pip-install `anthropic`:
  - Async: await LeadMagnetAgent(project_root="...").run(url)
  - Sync:  from agent import run_sync; run_sync(url)
  - CLI:   python agent_runner.py "url"

Result dict keys: markdown, pdf, docx, infographics, notion_url, raw_output
"""
from .agent import LeadMagnetAgent, run_sync

__all__ = ["LeadMagnetAgent", "run_sync"]
