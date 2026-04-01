"""
Lead Magnet Agent — CLI entry point.

Runs the full pipeline and prints results. Can be called directly,
piped into other tools, or invoked via subprocess from any language.

Usage:
    python agent_runner.py "https://notion.so/my-lead-magnet"
    python agent_runner.py "/path/to/document.pdf"
    python agent_runner.py "paste your content here..."

    # JSON-only output (no streaming text, for piping):
    python agent_runner.py --json "https://notion.so/my-lead-magnet"

Exit codes:
    0  Success
    1  Runtime error
    2  Missing environment variables
"""
import sys
import json
import asyncio
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agent import LeadMagnetAgent


def parse_args():
    parser = argparse.ArgumentParser(
        description="Abhay Singh Lead Magnet Generation Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="URL, file path, or pasted content",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_only",
        help="Output only the JSON result (suppresses streaming text)",
    )
    parser.add_argument(
        "--project-root",
        default=None,
        help="Path to the project root (default: directory of this script)",
    )
    parser.add_argument(
        "--no-notion",
        action="store_true",
        dest="no_notion",
        help="Skip pushing the result to Notion",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    if not args.input:
        print("Error: provide a URL, file path, or content as the first argument.", file=sys.stderr)
        print('Usage: python agent_runner.py "https://notion.so/..."', file=sys.stderr)
        sys.exit(1)

    project_root = args.project_root or str(Path(__file__).parent)
    try:
        agent = LeadMagnetAgent(project_root=project_root)
    except (EnvironmentError, FileNotFoundError) as e:
        print(f"Configuration error:\n{e}", file=sys.stderr)
        sys.exit(2)

    if not args.json_only:
        print("Lead Magnet Agent starting...")
        preview = args.input[:120] + ("..." if len(args.input) > 120 else "")
        print(f"Input: {preview}")
        print("-" * 60)

    async def on_message(text: str) -> None:
        if not args.json_only:
            print(text, end="", flush=True)

    result = await agent.run(args.input, on_message=on_message, push_to_notion=not args.no_notion)

    if not args.json_only:
        print("\n" + "=" * 60)
        print("OUTPUTS:")

    output = {k: v for k, v in result.items() if k != "raw_output"}
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(1)
