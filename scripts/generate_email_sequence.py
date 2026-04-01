"""
generate_email_sequence.py
Splits a lead magnet markdown file into a 5-part email micro-lesson sequence.

Each email is a standalone lesson with a hook, core insight, action item,
and CTA linking back to the full lead magnet or booking page.

Usage:
    python scripts/generate_email_sequence.py \
        --title "The /btw Playbook" \
        --content output/lead-magnet.md \
        --output output/email-sequence.md \
        --cta-url "https://calendly.com/abhaysinghnagarkoti11/new-meeting" \
        --notion-url "https://notion.so/your-page"
"""

import argparse
import re
import sys
from pathlib import Path


def load_markdown(content_input: str) -> str:
    if Path(content_input).is_file():
        return Path(content_input).read_text(encoding="utf-8")
    return content_input


def extract_sections(markdown: str) -> list[dict]:
    """Extract H2 sections from markdown with their content."""
    sections = []
    lines = markdown.split("\n")
    current_title = None
    current_lines = []

    for line in lines:
        h2_match = re.match(r"^##\s+(.+)", line)
        if h2_match:
            if current_title:
                sections.append({
                    "title": current_title,
                    "content": "\n".join(current_lines).strip()
                })
            current_title = h2_match.group(1).strip()
            current_lines = []
        elif current_title:
            current_lines.append(line)

    if current_title:
        sections.append({
            "title": current_title,
            "content": "\n".join(current_lines).strip()
        })

    return sections


def extract_stats_and_quotes(content: str) -> list[str]:
    """Pull out punchy stats, bold claims, and callout content."""
    highlights = []

    # Callout content
    for match in re.finditer(r"\[callout:[^\]]+\]\s*(.+)", content):
        highlights.append(match.group(1).strip())

    # Bold text
    for match in re.finditer(r"\*\*([^*]+)\*\*", content):
        text = match.group(1).strip()
        if len(text) > 15 and len(text) < 200:
            highlights.append(text)

    # Lines with numbers/percentages
    for line in content.split("\n"):
        line = line.strip()
        if re.search(r"\d+%|\$\d+|\d+x\b", line) and len(line) > 20 and len(line) < 200:
            clean = re.sub(r"^[-*\d.]+\s*", "", line).strip()
            if clean:
                highlights.append(clean)

    return list(dict.fromkeys(highlights))[:10]


def build_email_sequence(
    title: str,
    sections: list[dict],
    highlights: list[str],
    cta_url: str,
    notion_url: str | None = None,
) -> str:
    """Build a 5-email sequence from extracted sections."""

    num_sections = len(sections)
    emails_per_section = max(1, num_sections // 5)

    # Group sections into 5 email buckets
    email_groups = []
    for i in range(0, min(num_sections, 25), max(1, num_sections // 5)):
        end = min(i + emails_per_section, num_sections)
        group = sections[i:end]
        if group:
            email_groups.append(group)
        if len(email_groups) >= 5:
            break

    # Pad to 5 if needed
    while len(email_groups) < 5 and sections:
        email_groups.append([sections[-1]])

    output_lines = []
    output_lines.append(f"# Email Sequence: {title}\n")
    output_lines.append(f"**Source lead magnet:** {title}")
    output_lines.append(f"**Emails:** 5")
    output_lines.append(f"**Cadence:** Every 2 days recommended\n")
    output_lines.append("---\n")

    email_labels = [
        ("The Hook", "Introduce the core problem. Make them feel the pain."),
        ("The Framework", "Reveal the core system or approach. Give them the map."),
        ("The Deep Dive", "Go specific. Show the mechanics. Real examples."),
        ("The Proof", "Back it with data, results, case studies. Build trust."),
        ("The Close", "Recap the value. Clear CTA to book a call or get the full guide."),
    ]

    for idx, (label, purpose) in enumerate(email_labels):
        email_num = idx + 1
        group = email_groups[idx] if idx < len(email_groups) else email_groups[-1]
        section_titles = [g["title"] for g in group]
        section_content = "\n\n".join(g["content"] for g in group)

        # Pick a highlight for this email
        highlight = highlights[idx] if idx < len(highlights) else ""

        # Extract first 2-3 bullet points or sentences
        bullets = []
        for line in section_content.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                bullets.append(line)
            if len(bullets) >= 3:
                break

        # Build the email
        output_lines.append(f"## Email {email_num}: {label}\n")
        output_lines.append(f"**Purpose:** {purpose}")
        output_lines.append(f"**Covers:** {', '.join(section_titles)}\n")

        # Subject line
        if email_num == 1:
            output_lines.append(f"**Subject:** Most people waste money on this. Here's why.")
        elif email_num == 2:
            output_lines.append(f"**Subject:** The system behind {title.split(':')[0] if ':' in title else title}")
        elif email_num == 3:
            output_lines.append(f"**Subject:** Let me show you exactly how this works")
        elif email_num == 4:
            output_lines.append(f"**Subject:** The numbers don't lie")
        else:
            output_lines.append(f"**Subject:** Ready to stop doing this manually?")

        output_lines.append("")
        output_lines.append("**Body:**\n")

        if highlight:
            output_lines.append(f"> {highlight}\n")

        # Summarized key points
        if bullets:
            output_lines.append("Key takeaways from this lesson:\n")
            for b in bullets[:3]:
                output_lines.append(b)
            output_lines.append("")

        # CTA
        if email_num < 5:
            if notion_url:
                output_lines.append(f"Want the full breakdown? Read the complete guide: {notion_url}")
            output_lines.append(f"\nNext email in 2 days: we go deeper.\n")
        else:
            output_lines.append(f"That's the full system. If you want help implementing it:")
            output_lines.append(f"\nBook a free discovery call: {cta_url}\n")
            if notion_url:
                output_lines.append(f"Or grab the full guide: {notion_url}\n")

        output_lines.append("---\n")

    return "\n".join(output_lines)


def generate_email_sequence(
    title: str,
    content_input: str,
    output_path: str,
    cta_url: str = "https://calendly.com/abhaysinghnagarkoti11/new-meeting",
    notion_url: str | None = None,
):
    markdown = load_markdown(content_input)
    sections = extract_sections(markdown)

    if not sections:
        sys.exit("No H2 sections found in the content. Cannot build email sequence.")

    highlights = extract_stats_and_quotes(markdown)
    result = build_email_sequence(title, sections, highlights, cta_url, notion_url)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(result, encoding="utf-8")

    size_kb = Path(output_path).stat().st_size // 1024
    print(f"SUCCESS: {output_path} ({size_kb} KB, 5 emails)")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate 5-part email sequence from a lead magnet")
    parser.add_argument("--title", required=True, help="Lead magnet title")
    parser.add_argument("--content", required=True, help="Path to markdown file")
    parser.add_argument("--output", required=True, help="Output path for email sequence markdown")
    parser.add_argument("--cta-url", default="https://calendly.com/abhaysinghnagarkoti11/new-meeting",
                        help="CTA booking URL")
    parser.add_argument("--notion-url", default=None, help="Notion page URL for the full lead magnet")
    args = parser.parse_args()
    generate_email_sequence(args.title, args.content, args.output, args.cta_url, args.notion_url)
