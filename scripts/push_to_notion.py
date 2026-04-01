"""
push_to_notion.py
Creates a new Notion page from markdown content under the configured parent page.

Usage:
    python scripts/push_to_notion.py \
        --title "Your Lead Magnet Title" \
        --content path/to/content.md \
        --logo-path assets/abhay-logo.png \
        --cover-url "https://..."

Returns the URL of the newly created Notion page.
"""

import argparse
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from notion_client import Client
except ImportError:
    print("notion-client not installed. Run: pip install notion-client", file=sys.stderr)
    sys.exit(1)

try:
    import requests
except ImportError:
    print("requests not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass


NOTION_API_VERSION = "2022-06-28"

_LANG_MAP = {
    "bash": "bash", "sh": "bash", "shell": "bash",
    "json": "json", "python": "python", "py": "python",
    "javascript": "javascript", "js": "javascript",
    "typescript": "typescript", "ts": "typescript",
    "html": "html", "css": "css", "sql": "sql",
    "text": "plain text", "txt": "plain text",
}

_INLINE_MD_PATTERN = re.compile(
    r"\[([^\]]+)\]\(([^)]+)\)|\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|[^*`\[]+",
    re.UNICODE,
)


def _safe_url(url: str) -> str | None:
    """Return url if scheme is http/https, else log a warning and return None."""
    if url and url.lower().startswith(("https://", "http://")):
        return url
    print(f"[warn] Rejected non-http(s) URL: {url[:100]}", file=sys.stderr)
    return None


def _get_api_key() -> str:
    key = os.getenv("NOTION_API_KEY")
    if not key:
        raise ValueError("NOTION_API_KEY not set in .env")
    return key


def get_notion_client() -> Client:
    return Client(auth=_get_api_key())


def get_parent_page_id() -> str:
    page_id = os.getenv("NOTION_PARENT_PAGE_ID")
    if not page_id:
        raise ValueError("NOTION_PARENT_PAGE_ID not set in .env")
    return page_id


def try_upload_logo(logo_path: str | None) -> dict | None:
    """Upload logo via Notion Files API. Returns icon dict or None on failure."""
    if not logo_path or not os.path.isfile(logo_path):
        return None
    try:
        api_key = _get_api_key()
    except ValueError:
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    try:
        # Step 1: Create upload session
        resp = requests.post(
            "https://api.notion.com/v1/file_uploads",
            headers=headers,
            json={"name": Path(logo_path).name, "content_type": "image/png"}
        )
        if resp.status_code != 200:
            print(f"[icon] Files API returned {resp.status_code}, falling back to emoji", file=sys.stderr)
            return None

        data = resp.json()
        file_upload_id = data.get("id")
        upload_url = data.get("upload_url")

        if not file_upload_id or not upload_url:
            return None

        # Step 2: PUT the file
        with open(logo_path, "rb") as f:
            file_content = f.read()

        put_resp = requests.put(
            upload_url,
            headers={"Content-Type": "image/png"},
            data=file_content
        )

        if put_resp.status_code in [200, 204]:
            print(f"[icon] Logo uploaded successfully", file=sys.stderr)
            return {"type": "file_upload", "file_upload": {"id": file_upload_id}}
        else:
            print(f"[icon] Upload PUT returned {put_resp.status_code}, falling back to emoji", file=sys.stderr)
            return None

    except Exception as e:
        print(f"[icon] Upload failed ({e}), falling back to emoji", file=sys.stderr)
        return None


def rich_text(text: str) -> list:
    """Parse inline bold/italic/code/link markdown into Notion rich_text objects."""
    parts = []
    for match in _INLINE_MD_PATTERN.finditer(text):
        chunk = match.group(0)
        link_match = re.match(r"^\[([^\]]+)\]\(([^)]+)\)$", chunk)
        if link_match:
            link_text = link_match.group(1)
            link_url = _safe_url(link_match.group(2))
            if link_url:
                parts.append({
                    "type": "text",
                    "text": {"content": link_text, "link": {"url": link_url}},
                    "annotations": {"bold": True, "color": "blue"}
                })
            else:
                parts.append({"type": "text", "text": {"content": link_text}})
        elif chunk.startswith("**") and chunk.endswith("**"):
            parts.append({
                "type": "text",
                "text": {"content": chunk[2:-2]},
                "annotations": {"bold": True}
            })
        elif chunk.startswith("*") and chunk.endswith("*"):
            parts.append({
                "type": "text",
                "text": {"content": chunk[1:-1]},
                "annotations": {"italic": True}
            })
        elif chunk.startswith("`") and chunk.endswith("`"):
            parts.append({
                "type": "text",
                "text": {"content": chunk[1:-1]},
                "annotations": {"code": True}
            })
        else:
            if chunk:
                parts.append({"type": "text", "text": {"content": chunk}})
    return parts if parts else [{"type": "text", "text": {"content": text}}]


def heading_block(text: str, level: int) -> dict:
    type_map = {1: "heading_1", 2: "heading_2", 3: "heading_3"}
    block_type = type_map.get(level, "heading_2")
    return {
        "object": "block",
        "type": block_type,
        block_type: {"rich_text": rich_text(text), "color": "default"}
    }


def paragraph_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": rich_text(text)}
    }


def bullet_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": rich_text(text)}
    }


def numbered_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "numbered_list_item",
        "numbered_list_item": {"rich_text": rich_text(text)}
    }


def image_block(url: str, caption: str = "") -> dict:
    block = {
        "object": "block",
        "type": "image",
        "image": {
            "type": "external",
            "external": {"url": url}
        }
    }
    if caption:
        block["image"]["caption"] = [{"type": "text", "text": {"content": caption}}]
    return block


def callout_block(text: str, emoji: str = "💡") -> dict:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": rich_text(text),
            "icon": {"type": "emoji", "emoji": emoji},
            "color": "blue_background"
        }
    }


def quote_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "quote",
        "quote": {"rich_text": rich_text(text)}
    }


def parse_table_rows(lines: list, start: int) -> tuple[dict | None, int]:
    """
    Parse markdown table starting at lines[start].
    Returns (notion_table_block, next_line_index).
    """
    i = start
    rows = []

    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped.startswith("|"):
            break
        # Skip separator rows like |---|---|
        if re.match(r"^\|[-: |]+\|$", stripped):
            i += 1
            continue
        # Parse cells
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        rows.append(cells)
        i += 1

    if not rows:
        return None, start + 1

    table_width = max(len(r) for r in rows)

    # Pad rows to same width
    padded_rows = [r + [""] * (table_width - len(r)) for r in rows]

    # Build table_row blocks
    row_blocks = []
    for row in padded_rows:
        cells = [[{"type": "text", "text": {"content": cell}, "annotations": {"bold": False}}]
                 for cell in row]
        row_blocks.append({
            "object": "block",
            "type": "table_row",
            "table_row": {"cells": cells}
        })

    table_block = {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": table_width,
            "has_column_header": True,
            "has_row_header": False,
            "children": row_blocks
        }
    }

    return table_block, i


def markdown_to_notion_blocks(markdown_text: str) -> list:
    """
    Converts markdown text into Notion block objects.
    Supports: headings, paragraphs, bullets, numbered lists,
    dividers, tables, callouts, quotes.
    """
    blocks = []
    lines = markdown_text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # File placeholder: [file:filename.md] — creates a downloadable Notion file block
        file_match = re.match(r"^\[file:(.+?)\]$", stripped)
        if file_match:
            ref = file_match.group(1).strip()
            blocks.append({
                "__file_placeholder__": ref,
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": f"[File: {ref}]"}}]}
            })
            i += 1
            continue

        # Image placeholder: [image:filename.png] or [image:https://...]
        image_match = re.match(r"^\[image:(.+?)\]", stripped)
        if image_match:
            ref = image_match.group(1).strip()
            # If it's a URL, use directly. If filename, look in output/ folder.
            if ref.startswith("http"):
                safe_ref = _safe_url(ref)
                if safe_ref:
                    blocks.append(image_block(safe_ref))
            else:
                # Store as a placeholder paragraph — replaced at push time if URL available
                blocks.append({
                    "__image_placeholder__": ref,
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "text", "text": {"content": f"[Image: {ref}]"}}]}
                })
            i += 1
            continue

        # Callout: [callout:emoji] text
        callout_match = re.match(r"^\[callout:(.+?)\] (.+)$", stripped)
        if callout_match:
            emoji = callout_match.group(1)
            text = callout_match.group(2)
            blocks.append(callout_block(text, emoji))
            i += 1
            continue

        # Table
        if stripped.startswith("|") and not re.match(r"^\|[-: |]+\|$", stripped):
            table_block, i = parse_table_rows(lines, i)
            if table_block:
                blocks.append(table_block)
            continue

        # Fenced code block: ```lang ... ```
        if stripped.startswith("```"):
            lang = stripped[3:].strip().lower()
            notion_lang = _LANG_MAP.get(lang, "plain text")
            i += 1
            code_lines = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            code_content = "\n".join(code_lines)
            # Notion caps code block rich_text content at 2000 chars — split if needed
            max_len = 1999
            if len(code_content) <= max_len:
                chunks = [code_content]
            else:
                chunks = []
                while code_content:
                    chunks.append(code_content[:max_len])
                    code_content = code_content[max_len:]
            for chunk in chunks:
                blocks.append({
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": [{"type": "text", "text": {"content": chunk}}],
                        "language": notion_lang
                    }
                })
            if i < len(lines):
                i += 1  # skip closing ```
            else:
                print("[warn] Unclosed code block — treating remaining lines as code", file=sys.stderr)
                # Do not consume remaining content; break out and continue parsing
            continue

        # Bookmark: [bookmark:URL]
        bookmark_match = re.match(r"^\[bookmark:(.+?)\]$", stripped)
        if bookmark_match:
            url = _safe_url(bookmark_match.group(1).strip())
            if url:
                blocks.append({
                    "object": "block",
                    "type": "bookmark",
                    "bookmark": {"url": url}
                })
            i += 1
            continue

        if stripped.startswith("# "):
            blocks.append(heading_block(stripped[2:], level=1))
        elif stripped.startswith("## "):
            blocks.append(heading_block(stripped[3:], level=2))
        elif stripped.startswith("### "):
            blocks.append(heading_block(stripped[4:], level=3))
        elif stripped.startswith("#### "):
            blocks.append(heading_block(stripped[5:], level=3))
        elif stripped.startswith("---"):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        elif stripped.startswith("- [ ] ") or stripped.startswith("- [x] "):
            checked = stripped[3] == "x"
            text = stripped[6:]
            blocks.append({
                "object": "block",
                "type": "to_do",
                "to_do": {
                    "rich_text": rich_text(text),
                    "checked": checked
                }
            })
        elif stripped.startswith("- ") or stripped.startswith("* "):
            blocks.append(bullet_block(stripped[2:]))
        elif num_match := re.match(r"^\d+[.)]\s+(.+)$", stripped):
            blocks.append(numbered_block(num_match.group(1)))
        elif stripped.startswith("> "):
            blocks.append(quote_block(stripped[2:]))
        elif stripped == "":
            pass  # skip blank lines
        else:
            blocks.append(paragraph_block(stripped))

        i += 1

    return blocks


def upload_file_to_notion(api_key: str, file_path: str) -> str | None:
    """Upload a generic file (e.g. .md) to Notion Files API. Returns file_upload ID or None."""
    auth_headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
    }
    ext = Path(file_path).suffix.lower()
    content_type = "text/markdown" if ext == ".md" else "text/plain"

    try:
        resp = requests.post(
            "https://api.notion.com/v1/file_uploads",
            headers={**auth_headers, "Content-Type": "application/json"},
            json={"name": Path(file_path).name, "content_type": content_type}
        )
        if resp.status_code != 200:
            print(f"[file] Create upload session failed: {resp.status_code} {resp.text[:200]}", file=sys.stderr)
            return None
        data = resp.json()
        file_id = data.get("id")
        if not file_id:
            return None

        send_url = f"https://api.notion.com/v1/file_uploads/{file_id}/send"
        with open(file_path, "rb") as f:
            send_resp = requests.post(
                send_url,
                headers=auth_headers,
                files={"file": (Path(file_path).name, f, content_type)}
            )

        if send_resp.status_code == 200:
            return file_id
        else:
            print(f"[file] Send failed: {send_resp.status_code} {send_resp.text[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"[file] Upload failed for {file_path}: {e}", file=sys.stderr)
    return None


def upload_image_to_notion(api_key: str, image_path: str) -> str | None:
    """Upload a local image to Notion Files API. Returns file_upload ID or None."""
    auth_headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": "2022-06-28",
    }
    ext = Path(image_path).suffix.lower()
    content_type = "image/png" if ext == ".png" else "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"

    try:
        # Step 1: Create upload session
        resp = requests.post(
            "https://api.notion.com/v1/file_uploads",
            headers={**auth_headers, "Content-Type": "application/json"},
            json={"name": Path(image_path).name, "content_type": content_type}
        )
        if resp.status_code != 200:
            print(f"[image] Create upload session failed: {resp.status_code} {resp.text[:200]}", file=sys.stderr)
            return None
        data = resp.json()
        file_id = data.get("id")
        if not file_id:
            return None

        # Step 2: POST multipart to /send endpoint
        send_url = f"https://api.notion.com/v1/file_uploads/{file_id}/send"
        with open(image_path, "rb") as f:
            send_resp = requests.post(
                send_url,
                headers=auth_headers,
                files={"file": (Path(image_path).name, f, content_type)}
            )

        if send_resp.status_code == 200:
            return file_id
        else:
            print(f"[image] Send failed: {send_resp.status_code} {send_resp.text[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"[image] Upload failed for {image_path}: {e}", file=sys.stderr)
    return None


def push_to_notion(
    title: str,
    content_input: str,
    logo_path: str | None = None,
    cover_url: str | None = None,
    icon_emoji: str = "🎯",
    images_dir: str | None = None
) -> str:
    """
    Creates a Notion page and returns its URL.
    content_input: file path or raw markdown string.
    """
    notion = get_notion_client()
    parent_id = get_parent_page_id()

    if os.path.isfile(content_input):
        markdown_text = Path(content_input).read_text(encoding="utf-8")
    else:
        markdown_text = content_input

    blocks = markdown_to_notion_blocks(markdown_text)

    # --- Resolve image placeholders ---
    api_key = _get_api_key()
    _root = Path(__file__).parent.parent
    _default_dirs = [str(_root / "output"), str(_root / "assets")]
    search_dirs = [images_dir] + _default_dirs if images_dir else _default_dirs
    skipped_images = []

    # First pass: resolve file paths for all image placeholders
    image_jobs = []  # (idx, placeholder, found_path)
    for idx, block in enumerate(blocks):
        placeholder = block.get("__image_placeholder__")
        if not placeholder:
            continue
        # Use only the basename to prevent path traversal (e.g. ../../../sensitive-file)
        safe_name = Path(placeholder).name
        found_path = None
        for d in search_dirs:
            if d and os.path.isdir(d):
                candidate = os.path.join(d, safe_name)
                if os.path.isfile(candidate):
                    found_path = candidate
                    break
        if found_path:
            image_jobs.append((idx, placeholder, found_path))
        else:
            print(f"[image] Not found: {placeholder} — skipping", file=sys.stderr)
            blocks[idx] = None
            skipped_images.append(placeholder)

    # Second pass: upload all images in parallel
    if image_jobs:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(upload_image_to_notion, api_key, path): (idx, placeholder)
                for idx, placeholder, path in image_jobs
            }
            for future in as_completed(futures):
                idx, placeholder = futures[future]
                try:
                    file_id = future.result()
                    if file_id:
                        blocks[idx] = {
                            "object": "block",
                            "type": "image",
                            "image": {"type": "file_upload", "file_upload": {"id": file_id}}
                        }
                        print(f"[image] Uploaded {placeholder}", file=sys.stderr)
                    else:
                        blocks[idx] = None
                        skipped_images.append(placeholder)
                except Exception as e:
                    print(f"[image] Upload failed for {placeholder}: {e}", file=sys.stderr)
                    blocks[idx] = None
                    skipped_images.append(placeholder)

    if skipped_images:
        print(f"WARNING: {len(skipped_images)} image(s) not embedded: {', '.join(skipped_images)}", file=sys.stderr)

    # --- Resolve file placeholders ---
    skipped_files = []
    file_jobs = []
    for idx, block in enumerate(blocks):
        placeholder = block.get("__file_placeholder__") if isinstance(block, dict) else None
        if not placeholder:
            continue
        safe_name = Path(placeholder).name
        found_path = None
        for d in search_dirs:
            if d and os.path.isdir(d):
                candidate = os.path.join(d, safe_name)
                if os.path.isfile(candidate):
                    found_path = candidate
                    break
        if found_path:
            file_jobs.append((idx, placeholder, found_path))
        else:
            print(f"[file] Not found: {placeholder} — skipping", file=sys.stderr)
            blocks[idx] = None
            skipped_files.append(placeholder)

    if file_jobs:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(upload_file_to_notion, api_key, path): (idx, placeholder)
                for idx, placeholder, path in file_jobs
            }
            for future in as_completed(futures):
                idx, placeholder = futures[future]
                try:
                    file_id = future.result()
                    if file_id:
                        blocks[idx] = {
                            "object": "block",
                            "type": "file",
                            "file": {
                                "type": "file_upload",
                                "file_upload": {"id": file_id},
                                "name": Path(placeholder).name
                            }
                        }
                        print(f"[file] Uploaded {placeholder}", file=sys.stderr)
                    else:
                        blocks[idx] = None
                        skipped_files.append(placeholder)
                except Exception as e:
                    print(f"[file] Upload failed for {placeholder}: {e}", file=sys.stderr)
                    blocks[idx] = None
                    skipped_files.append(placeholder)

    if skipped_files:
        print(f"WARNING: {len(skipped_files)} file(s) not embedded: {', '.join(skipped_files)}", file=sys.stderr)

    blocks = [b for b in blocks if b is not None]

    # --- Icon ---
    icon = try_upload_logo(logo_path) if logo_path else None
    if icon is None:
        icon = {"type": "emoji", "emoji": icon_emoji}

    # --- Cover ---
    cover = None
    if cover_url:
        safe_cover = _safe_url(cover_url)
        if safe_cover:
            cover = {"type": "external", "external": {"url": safe_cover}}

    # --- Build page payload ---
    page_payload = {
        "parent": {"page_id": parent_id},
        "icon": icon,
        "properties": {
            "title": {
                "title": [{"type": "text", "text": {"content": title}}]
            }
        },
        "children": []
    }
    if cover:
        page_payload["cover"] = cover

    # Notion API limit: 100 blocks per request
    chunk_size = 100
    first_chunk = blocks[:chunk_size]
    remaining_chunks = [blocks[j:j+chunk_size] for j in range(chunk_size, len(blocks), chunk_size)]

    page_payload["children"] = first_chunk

    try:
        response = notion.pages.create(**page_payload)
    except Exception as e:
        sys.exit(f"ERROR: Notion page creation failed: {e}")
    page_id = response["id"]

    # Append remaining blocks with exponential back-off retry (handles 429 rate limits)
    for chunk in remaining_chunks:
        for attempt in range(3):
            try:
                notion.blocks.children.append(block_id=page_id, children=chunk)
                break
            except Exception as e:
                if attempt == 2:
                    print(f"[warn] Failed to append block chunk after 3 attempts: {e}", file=sys.stderr)
                else:
                    time.sleep(2 ** attempt)  # 1s, 2s back-off before retrying

    page_url = response.get("url", f"https://notion.so/{page_id.replace('-', '')}")
    return page_url


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Push lead magnet content to Notion")
    parser.add_argument("--title", required=True, help="Page title")
    parser.add_argument("--content", required=True, help="Path to markdown file OR raw markdown string")
    parser.add_argument("--logo-path", default=None, help="Path to logo PNG for page icon")
    parser.add_argument("--cover-url", default=None, help="External URL for page cover image")
    parser.add_argument("--icon-emoji", default="🎯", help="Fallback emoji icon if logo upload fails")

    parser.add_argument("--images-dir", default=None, help="Directory to look for infographic image files")
    args = parser.parse_args()
    url = push_to_notion(
        title=args.title,
        content_input=args.content,
        logo_path=args.logo_path,
        cover_url=args.cover_url,
        icon_emoji=args.icon_emoji,
        images_dir=args.images_dir
    )
    print(url)
