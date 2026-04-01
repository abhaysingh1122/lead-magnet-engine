"""
generate_social_posts.py
Extracts key insights from a lead magnet and generates LinkedIn posts
and Twitter/X threads ready to copy-paste.

Usage:
    python scripts/generate_social_posts.py \
        --title "The /btw Playbook" \
        --content output/lead-magnet.md \
        --output output/social-posts.md \
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


def extract_h2_titles(markdown: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"^##\s+(.+)", markdown, re.MULTILINE)]


def extract_stats(markdown: str) -> list[str]:
    """Pull lines with concrete numbers, percentages, dollar amounts."""
    stats = []
    for line in markdown.split("\n"):
        line = line.strip()
        if re.search(r"\d+%|\$[\d,.]+|\d+x\b|\d+\s*hours?|\d+\s*minutes?|\d+\s*days?", line):
            clean = re.sub(r"^[-*|>\d.]+\s*", "", line).strip()
            clean = re.sub(r"\[callout:[^\]]+\]\s*", "", clean).strip()
            if 20 < len(clean) < 250 and not clean.startswith("#"):
                stats.append(clean)
    return list(dict.fromkeys(stats))[:15]


def extract_callouts(markdown: str) -> list[str]:
    """Extract callout block content."""
    callouts = []
    for match in re.finditer(r"\[callout:[^\]]+\]\s*(.+)", markdown):
        text = match.group(1).strip()
        if len(text) > 20:
            callouts.append(text)
    return callouts[:10]


def extract_bold_claims(markdown: str) -> list[str]:
    """Extract bold text that reads like standalone claims."""
    claims = []
    for match in re.finditer(r"\*\*([^*]{20,150})\*\*", markdown):
        text = match.group(1).strip()
        if not text.startswith("Subject") and not text.startswith("Purpose"):
            claims.append(text)
    return list(dict.fromkeys(claims))[:10]


def extract_table_rows(markdown: str) -> list[str]:
    """Pull interesting table data as formatted strings."""
    rows = []
    for line in markdown.split("\n"):
        line = line.strip()
        if line.startswith("|") and not re.match(r"^\|[-:\s|]+\|$", line):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 2 and any(re.search(r"\d", c) for c in cells):
                row_text = " ".join(c for c in cells if c)
                if len(row_text) > 10:
                    rows.append(row_text)
    return rows[:10]


def build_linkedin_posts(
    title: str,
    stats: list[str],
    callouts: list[str],
    claims: list[str],
    sections: list[str],
    cta_url: str,
    notion_url: str | None,
) -> list[str]:
    """Generate 3 LinkedIn post drafts."""
    posts = []

    # Post 1: The Hook Post (stat-driven)
    post1_lines = []
    if stats:
        post1_lines.append(f"{stats[0]}\n")
    post1_lines.append(f"I wrote a full breakdown on this: {title}\n")
    post1_lines.append("Here's what most people get wrong:\n")
    for claim in claims[:3]:
        post1_lines.append(f"  {claim}")
    post1_lines.append("")
    if notion_url:
        post1_lines.append(f"Full guide (free): {notion_url}")
    post1_lines.append(f"\nWant help implementing this? {cta_url}")
    post1_lines.append("\n#automation #ai #systems #agencylife")
    posts.append("\n".join(post1_lines))

    # Post 2: The Listicle (framework breakdown)
    post2_lines = []
    post2_lines.append(f"I just published: {title}\n")
    post2_lines.append("What's inside:\n")
    for i, section in enumerate(sections[:6], 1):
        if "CTA" not in section and "Want Help" not in section:
            post2_lines.append(f"{i}. {section}")
    post2_lines.append("")
    if stats and len(stats) > 1:
        post2_lines.append(f"Key finding: {stats[1]}\n")
    if notion_url:
        post2_lines.append(f"Read it here: {notion_url}")
    post2_lines.append("\n#contentmarketing #leadgeneration #b2b")
    posts.append("\n".join(post2_lines))

    # Post 3: The Insight Post (callout-driven)
    post3_lines = []
    if callouts:
        post3_lines.append(f"{callouts[0]}\n")
    elif stats:
        post3_lines.append(f"{stats[0]}\n")
    post3_lines.append("Most people overcomplicate this.\n")
    post3_lines.append("The fix is simpler than you think:\n")
    for stat in stats[1:4]:
        post3_lines.append(f"  {stat}")
    post3_lines.append(f"\nI broke down the full system in a free playbook.")
    if notion_url:
        post3_lines.append(f"\nGrab it: {notion_url}")
    post3_lines.append(f"\nOr book a call and I'll walk you through it: {cta_url}")
    post3_lines.append("\n#automation #systems #agency")
    posts.append("\n".join(post3_lines))

    return posts


def build_twitter_thread(
    title: str,
    stats: list[str],
    callouts: list[str],
    claims: list[str],
    sections: list[str],
    cta_url: str,
    notion_url: str | None,
) -> list[str]:
    """Generate a Twitter/X thread (8-12 tweets)."""
    tweets = []

    # Tweet 1: Hook
    hook = stats[0] if stats else f"I just published: {title}"
    tweets.append(f"1/ {hook}\n\nA thread on what I found:")

    # Tweet 2: What this is
    tweets.append(f"2/ I wrote a full breakdown: {title}\n\nHere's the TL;DR (thread):")

    # Tweets 3-7: One section per tweet
    tweet_num = 3
    for section in sections[:5]:
        if "CTA" not in section and "Want Help" not in section and "Action Checklist" not in section:
            tweet_text = f"{tweet_num}/ {section}"
            # Add a relevant stat if available
            stat_idx = tweet_num - 3
            if stat_idx < len(stats):
                tweet_text += f"\n\n{stats[stat_idx]}"
            tweets.append(tweet_text)
            tweet_num += 1

    # Tweet: Key insight
    if callouts:
        tweets.append(f"{tweet_num}/ Key insight:\n\n{callouts[0]}")
        tweet_num += 1

    # Tweet: Bold claim
    if claims:
        tweets.append(f"{tweet_num}/ {claims[0]}")
        tweet_num += 1

    # Final tweet: CTA
    cta_tweet = f"{tweet_num}/ That's the system.\n\n"
    if notion_url:
        cta_tweet += f"Full guide (free): {notion_url}\n\n"
    cta_tweet += f"Want help building this? Book a call: {cta_url}\n\n"
    cta_tweet += "Like + repost if this was useful."
    tweets.append(cta_tweet)

    return tweets


def generate_social_posts(
    title: str,
    content_input: str,
    output_path: str,
    cta_url: str = "https://calendly.com/abhaysinghnagarkoti11/new-meeting",
    notion_url: str | None = None,
):
    markdown = load_markdown(content_input)

    sections = extract_h2_titles(markdown)
    stats = extract_stats(markdown)
    callouts = extract_callouts(markdown)
    claims = extract_bold_claims(markdown)
    table_rows = extract_table_rows(markdown)

    if not sections:
        sys.exit("No H2 sections found in content. Cannot generate social posts.")

    # Combine stats + table rows for richer data
    all_stats = stats + table_rows
    all_stats = list(dict.fromkeys(all_stats))[:15]

    linkedin_posts = build_linkedin_posts(
        title, all_stats, callouts, claims, sections, cta_url, notion_url
    )
    twitter_thread = build_twitter_thread(
        title, all_stats, callouts, claims, sections, cta_url, notion_url
    )

    # Build output
    output_lines = []
    output_lines.append(f"# Social Posts: {title}\n")
    output_lines.append(f"**Source:** {title}")
    output_lines.append(f"**Generated:** 3 LinkedIn posts + 1 Twitter thread\n")
    output_lines.append("---\n")

    # LinkedIn posts
    output_lines.append("# LinkedIn Posts\n")
    for i, post in enumerate(linkedin_posts, 1):
        output_lines.append(f"## LinkedIn Post {i}\n")
        output_lines.append("```")
        output_lines.append(post)
        output_lines.append("```\n")
        char_count = len(post)
        output_lines.append(f"*{char_count} characters*\n")
        output_lines.append("---\n")

    # Twitter thread
    output_lines.append("# Twitter/X Thread\n")
    for tweet in twitter_thread:
        output_lines.append("```")
        output_lines.append(tweet)
        output_lines.append("```\n")

    result = "\n".join(output_lines)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(result, encoding="utf-8")

    size_kb = Path(output_path).stat().st_size // 1024
    print(f"SUCCESS: {output_path} ({size_kb} KB, {len(linkedin_posts)} LinkedIn + {len(twitter_thread)} tweets)")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate LinkedIn posts + Twitter thread from a lead magnet")
    parser.add_argument("--title", required=True, help="Lead magnet title")
    parser.add_argument("--content", required=True, help="Path to markdown file")
    parser.add_argument("--output", required=True, help="Output path for social posts markdown")
    parser.add_argument("--cta-url", default="https://calendly.com/abhaysinghnagarkoti11/new-meeting",
                        help="CTA booking URL")
    parser.add_argument("--notion-url", default=None, help="Notion page URL for the full lead magnet")
    args = parser.parse_args()
    generate_social_posts(args.title, args.content, args.output, args.cta_url, args.notion_url)
