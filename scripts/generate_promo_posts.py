"""
generate_promo_posts.py
Generates promotional posts for LinkedIn and Twitter/X that promote a lead magnet.
These are the posts that drive DMs, comments, or clicks to receive the free content.

NOT value posts. NOT content extraction. These are SALES posts for the lead magnet.

Outputs per run:
  - 2 LinkedIn promo posts (different templates)
  - 1 LinkedIn soft-sell PS post
  - 1 Twitter/X promo thread
  - 1 Twitter/X single-tweet promo

Templates based on research from top-performing LinkedIn lead magnet campaigns.

Usage:
    python scripts/generate_promo_posts.py \
        --title "The /btw Playbook" \
        --content output/lead-magnet.md \
        --output output/promo-posts.md \
        --keyword "PLAYBOOK" \
        --cta-type comment_keyword \
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


def extract_h2_titles(markdown: str) -> list[str]:
    titles = []
    for m in re.finditer(r"^##\s+(.+)", markdown, re.MULTILINE):
        t = m.group(1).strip()
        if "Want Help" not in t and "Action Checklist" not in t and "FAQ" not in t:
            titles.append(t)
    return titles


def extract_stats(markdown: str) -> list[str]:
    stats = []
    for line in markdown.split("\n"):
        line = line.strip()
        if re.search(r"\d+%|\$[\d,.]+|\d+x\b|\d+\s*hours?|\d+\s*minutes?|\d+\s*days?", line):
            clean = re.sub(r"^[-*|>\d.]+\s*", "", line).strip()
            clean = re.sub(r"\[callout:[^\]]+\]\s*", "", clean).strip()
            if 20 < len(clean) < 200 and not clean.startswith("#") and not clean.startswith("|"):
                stats.append(clean)
    return list(dict.fromkeys(stats))[:10]


def extract_callouts(markdown: str) -> list[str]:
    callouts = []
    for match in re.finditer(r"\[callout:[^\]]+\]\s*(.+)", markdown):
        text = match.group(1).strip()
        if len(text) > 20 and len(text) < 200:
            callouts.append(text)
    return callouts[:5]


def extract_problems(markdown: str) -> list[str]:
    """Extract problem statements, mistakes, or pain points."""
    problems = []
    patterns = [
        r"(?:most|many)\s+(?:people|teams|agencies|companies)\s+(.{20,120})",
        r"(?:the\s+problem|the\s+issue|the\s+mistake)\s+(?:is|with)\s+(.{20,120})",
        r"(?:wrong|broken|failing|struggle|waste)\s+(.{15,100})",
    ]
    for line in markdown.split("\n"):
        line_lower = line.strip().lower()
        for pattern in patterns:
            match = re.search(pattern, line_lower)
            if match:
                # Truncate at sentence boundary, max 100 chars
                text = line.strip()[:150]
                sentence_end = max(text.rfind(". "), text.rfind("? "), text.rfind("! "))
                if sentence_end > 30:
                    text = text[:sentence_end + 1]
                problems.append(text)
                break
    return list(dict.fromkeys(problems))[:5]


def detect_resource_type(title: str) -> str:
    title_lower = title.lower()
    if "playbook" in title_lower:
        return "playbook"
    elif "framework" in title_lower:
        return "framework"
    elif "guide" in title_lower:
        return "guide"
    elif "template" in title_lower:
        return "template"
    elif "checklist" in title_lower:
        return "checklist"
    elif "audit" in title_lower:
        return "audit"
    elif "blueprint" in title_lower:
        return "blueprint"
    return "guide"


def build_cta_line(cta_type: str, keyword: str, notion_url: str | None) -> str:
    """Build the CTA line based on gating type."""
    if cta_type == "comment_keyword":
        return f'Comment "{keyword}" below and I\'ll DM you the link.'
    elif cta_type == "dm_keyword":
        return f'DM me "{keyword}" and I\'ll send it over.'
    elif cta_type == "link_in_comments":
        return "Link in the first comment. Go grab it."
    elif cta_type == "link_direct" and notion_url:
        return f"Grab it here: {notion_url}"
    else:
        return f'Comment "{keyword}" below and I\'ll send it to you.'


# ── LINKEDIN TEMPLATES ────────────────────────────────────────────────────────


def linkedin_effort_flex(
    title: str, resource_type: str, sections: list[str],
    stats: list[str], cta_line: str, keyword: str,
) -> str:
    """Template A: The Effort Flex — "I spent X hours building this" """
    lines = []

    # Hook
    if stats:
        lines.append(f"{stats[0]}")
        lines.append("")
        lines.append(f"I built an entire {resource_type} around this.")
    else:
        lines.append(f"I just spent weeks building a free {resource_type}.")
    lines.append("")

    # Value stack
    lines.append(f'It\'s called "{title}"\n')
    lines.append("Here's what's inside:\n")

    for i, section in enumerate(sections[:5], 1):
        lines.append(f"{i}. {section}")

    lines.append("")

    # Second stat if available
    if len(stats) > 1:
        lines.append(f"{stats[1]}")
        lines.append("")

    # CTA
    lines.append(f"It's free. No email needed.\n")
    lines.append(cta_line)

    return "\n".join(lines)


def linkedin_problem_solution(
    title: str, resource_type: str, sections: list[str],
    stats: list[str], problems: list[str], callouts: list[str],
    cta_line: str, keyword: str,
) -> str:
    """Template B: Problem-Solution Tease"""
    lines = []

    # Hook (contrarian or stat)
    if callouts:
        lines.append(callouts[0])
    elif stats:
        lines.append(stats[0])
    else:
        lines.append(f"Most agencies are doing this wrong.")
    lines.append("")

    # Problem
    lines.append("Here's what I keep seeing:\n")
    if problems:
        for p in problems[:3]:
            clean = re.sub(r"^[-*]+\s*", "", p).strip()
            lines.append(f"  {clean}")
    else:
        lines.append("  Teams wasting hours on manual work that should be automated.")
        lines.append("  Systems that break when one person is out.")
        lines.append("  Tools connected with duct tape and prayers.")
    lines.append("")

    # Solution tease
    lines.append(f"I built a {resource_type} that addresses all of this.\n")
    lines.append("Inside you'll find:\n")
    for section in sections[:4]:
        lines.append(f"  {section}")
    lines.append("")

    # CTA
    lines.append(f"It's completely free.\n")
    lines.append(cta_line)

    return "\n".join(lines)


def linkedin_ps_soft_sell(
    title: str, resource_type: str,
    stats: list[str], callouts: list[str], sections: list[str],
    cta_line: str, keyword: str,
) -> str:
    """Template G: PS Line CTA — soft sell on a value post"""
    lines = []

    # Value content (not about the lead magnet — standalone insight)
    if stats:
        lines.append(stats[0])
    elif callouts:
        lines.append(callouts[0])
    lines.append("")

    # Teach something from the content
    lines.append("Here's what most people miss:\n")
    for section in sections[:3]:
        lines.append(f"  {section}")
    lines.append("")

    if len(stats) > 1:
        lines.append(stats[1])
        lines.append("")

    lines.append("That's the short version.\n")

    # PS line
    lines.append("---\n")
    section_count = len(sections)
    lines.append(f"P.S. I turned this into a full {resource_type} with {section_count}+ sections covering everything above in detail.\n")
    lines.append(f'DM me "{keyword}" if you want it. It\'s free.')

    return "\n".join(lines)


# ── TWITTER TEMPLATES ─────────────────────────────────────────────────────────


def twitter_promo_thread(
    title: str, resource_type: str, sections: list[str],
    stats: list[str], callouts: list[str],
    cta_line: str, keyword: str, notion_url: str | None,
) -> list[str]:
    """Full Twitter/X promo thread (5-8 tweets)"""
    tweets = []

    # Tweet 1: Hook
    hook = stats[0] if stats else f"I just built something I wish I had 6 months ago."
    tweets.append(f"{hook}\n\nI turned it into a free {resource_type}.\n\nHere's what's inside:")

    # Tweets 2-5: Value tease (one section per tweet)
    for i, section in enumerate(sections[:4]):
        stat = f"\n\n{stats[i+1]}" if i+1 < len(stats) else ""
        tweets.append(f"{section}{stat}")

    # Tweet: Social proof or key insight
    if callouts:
        tweets.append(f"{callouts[0]}")

    # Final tweet: CTA
    cta_tweet = f'That\'s "{title}"\n\n'
    cta_tweet += f"It's free. No email. No catch.\n\n"
    cta_tweet += f'Reply "{keyword}" and I\'ll DM it to you.\n\n'
    cta_tweet += "Like + RT so others can find this."
    tweets.append(cta_tweet)

    # Number the tweets
    numbered = [f"{i+1}/ {t}" for i, t in enumerate(tweets)]
    return numbered


def twitter_single_tweet(
    title: str, resource_type: str, sections: list[str],
    keyword: str, notion_url: str | None,
) -> str:
    """Single tweet lead magnet promo"""
    lines = []
    lines.append(f"I just released a free {resource_type}:\n")
    lines.append(f'"{title}"\n')
    lines.append("Inside:")
    for section in sections[:4]:
        lines.append(f"  {section}")
    lines.append("")
    lines.append(f'Reply "{keyword}" and I\'ll DM you.\n')
    lines.append("(Like + RT to help others find it)")

    return "\n".join(lines)


# ── MAIN ──────────────────────────────────────────────────────────────────────


def generate_promo_posts(
    title: str,
    content_input: str,
    output_path: str,
    keyword: str = "GUIDE",
    cta_type: str = "comment_keyword",
    notion_url: str | None = None,
):
    markdown = load_markdown(content_input)

    sections = extract_h2_titles(markdown)
    stats = extract_stats(markdown)
    callouts = extract_callouts(markdown)
    problems = extract_problems(markdown)
    resource_type = detect_resource_type(title)

    if not sections:
        sys.exit("No H2 sections found in content. Cannot generate promo posts.")

    keyword = keyword.upper()
    cta_line = build_cta_line(cta_type, keyword, notion_url)

    # Generate all posts
    li_effort = linkedin_effort_flex(title, resource_type, sections, stats, cta_line, keyword)
    li_problem = linkedin_problem_solution(title, resource_type, sections, stats, problems, callouts, cta_line, keyword)
    li_ps = linkedin_ps_soft_sell(title, resource_type, stats, callouts, sections, cta_line, keyword)
    tw_thread = twitter_promo_thread(title, resource_type, sections, stats, callouts, cta_line, keyword, notion_url)
    tw_single = twitter_single_tweet(title, resource_type, sections, keyword, notion_url)

    # Build output
    output = []
    output.append(f"# Promo Posts: {title}\n")
    output.append(f"**Resource type:** {resource_type}")
    output.append(f"**DM keyword:** {keyword}")
    output.append(f"**CTA type:** {cta_type}")
    if notion_url:
        output.append(f"**Notion URL:** {notion_url}")
    output.append(f"**Generated:** 2 LinkedIn promo + 1 LinkedIn soft-sell + 1 Twitter thread + 1 Twitter single\n")
    output.append("---\n")

    # LinkedIn
    output.append("# LinkedIn Promotional Posts\n")

    output.append('## LinkedIn Post 1: "The Effort Flex"\n')
    output.append("```")
    output.append(li_effort)
    output.append("```\n")
    output.append(f"*{len(li_effort)} characters*\n")
    output.append("---\n")

    output.append('## LinkedIn Post 2: "Problem-Solution Tease"\n')
    output.append("```")
    output.append(li_problem)
    output.append("```\n")
    output.append(f"*{len(li_problem)} characters*\n")
    output.append("---\n")

    output.append('## LinkedIn Post 3: "PS Line Soft Sell"\n')
    output.append("```")
    output.append(li_ps)
    output.append("```\n")
    output.append(f"*{len(li_ps)} characters*\n")
    output.append("---\n")

    # Twitter
    output.append("# Twitter/X Promotional Posts\n")

    output.append("## Twitter Promo Thread\n")
    for tweet in tw_thread:
        output.append("```")
        output.append(tweet)
        output.append("```\n")

    output.append("---\n")

    output.append("## Twitter Single-Tweet Promo\n")
    output.append("```")
    output.append(tw_single)
    output.append("```\n")
    output.append(f"*{len(tw_single)} characters*\n")

    result = "\n".join(output)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(result, encoding="utf-8")

    size_kb = Path(output_path).stat().st_size // 1024
    print(f"SUCCESS: {output_path} ({size_kb} KB, 3 LinkedIn + 1 thread + 1 tweet)")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate lead magnet promotional posts for LinkedIn + Twitter")
    parser.add_argument("--title", required=True, help="Lead magnet title")
    parser.add_argument("--content", required=True, help="Path to markdown file")
    parser.add_argument("--output", required=True, help="Output path for promo posts markdown")
    parser.add_argument("--keyword", default="GUIDE", help="DM trigger keyword (ALL CAPS). E.g. PLAYBOOK, GUIDE, SYSTEM")
    parser.add_argument("--cta-type", default="comment_keyword",
                        choices=["comment_keyword", "dm_keyword", "link_in_comments", "link_direct"],
                        help="CTA gating type")
    parser.add_argument("--notion-url", default=None, help="Notion page URL for direct link CTA")
    args = parser.parse_args()
    generate_promo_posts(args.title, args.content, args.output, args.keyword, args.cta_type, args.notion_url)
