"""
fetch_content.py
Universal content fetcher. Handles:
  - Notion public pages (unofficial API)
  - Google Docs (export URL trick)
  - Google Drive (export URL trick)
  - PDF files (pdfplumber)
  - Any public URL (requests + BeautifulSoup)

Usage:
    python scripts/fetch_content.py --input "https://notion.so/..."
    python scripts/fetch_content.py --input "path/to/file.pdf"
    python scripts/fetch_content.py --input "https://docs.google.com/..."

Returns clean plain text to stdout.
"""

import argparse
import hashlib
import ipaddress
import json
import re
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

# Maximum response body size accepted from any remote URL (10 MB)
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024


def _is_private_url(url: str) -> bool:
    """Return True if url resolves to a private/loopback/link-local address."""
    try:
        host = url.split("//", 1)[1].split("/")[0].split(":")[0]
        ip = ipaddress.ip_address(socket.gethostbyname(host))
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except Exception:
        return True  # fail closed

# Recognised image file extensions for URL extraction
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp")

# ─── CACHE ─────────────────────────────────────────────────────────────────────

_CACHE_DIR = Path(__file__).parent.parent / "output" / ".cache"
_CACHE_TTL = 15 * 60  # 15 minutes


def _cache_key(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


def _cache_get(url: str) -> str | None:
    cache_file = _CACHE_DIR / f"{_cache_key(url)}.json"
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        age = time.time() - data["ts"]
        if age < _CACHE_TTL:
            remaining = int((_CACHE_TTL - age) / 60)
            print(f"[cache] HIT — {remaining}m remaining (use --no-cache to bypass)", file=sys.stderr)
            return data["content"]
        print("[cache] EXPIRED — refetching", file=sys.stderr)
    except Exception:
        pass
    return None


def _cache_set(url: str, content: str) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = _CACHE_DIR / f"{_cache_key(url)}.json"
    cache_file.write_text(json.dumps({"ts": time.time(), "content": content}), encoding="utf-8")

# ─── NOTION ────────────────────────────────────────────────────────────────────

def extract_notion_page_id(url: str) -> str | None:
    """Extract the 32-char hex page ID from any Notion URL format."""
    # Match 32-char hex at end of URL path
    match = re.search(r'([a-f0-9]{32})(?:[?#]|$)', url)
    if match:
        raw = match.group(1)
        return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"
    return None


def _notion_load_page_chunk(page_id: str) -> dict:
    """Hit the Notion unofficial API and return the full block map, paginating through all chunks."""
    api_url = "https://www.notion.so/api/v3/loadPageChunk"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    all_blocks = {}
    cursor = {"stack": []}
    chunk_number = 0
    while True:
        body = {
            "pageId": page_id,
            "limit": 300,
            "cursor": cursor,
            "chunkNumber": chunk_number,
            "verticalColumns": False,
        }
        resp = requests.post(api_url, headers=headers, json=body, timeout=20)
        if resp.status_code != 200:
            sys.exit(f"Notion API error {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        new_blocks = data.get("recordMap", {}).get("block", {})
        all_blocks.update(new_blocks)
        next_cursor = data.get("cursor", {})
        if not next_cursor or not next_cursor.get("stack") or chunk_number > 20:
            break
        cursor = next_cursor
        chunk_number += 1
    return all_blocks


def fetch_notion(url: str, no_cache: bool = False) -> str:
    """Fetch a public Notion page via unofficial API, recursing into sub-pages."""
    if not no_cache:
        cached = _cache_get(url)
        if cached is not None:
            return cached

    page_id = extract_notion_page_id(url)
    if not page_id:
        sys.exit(f"Could not extract Notion page ID from URL: {url}")

    blocks = _notion_load_page_chunk(page_id)
    if not blocks:
        sys.exit("No content found. The page may be private or empty.")

    content = notion_blocks_to_markdown(blocks, page_id)
    _cache_set(url, content)
    return content


def get_notion_text(props: dict) -> str:
    title = props.get("title", [])
    parts = []
    for chunk in title:
        if isinstance(chunk, list) and chunk:
            parts.append(str(chunk[0]))
    return "".join(parts)


def _render_notion_table(blocks: dict, table_id: str) -> list:
    """Render a Notion table block as markdown rows."""
    table_block = blocks.get(table_id, {}).get("value", {})
    row_ids = table_block.get("content", [])
    if not row_ids:
        return []

    fmt = table_block.get("format", {})
    col_order = fmt.get("table_block_column_order", [])

    def _cell_text(cell_value):
        """Extract plain text from a Notion table cell value (list of chunks)."""
        parts = []
        for chunk in (cell_value or []):
            if isinstance(chunk, list) and chunk:
                parts.append(str(chunk[0]))
        return "".join(parts)

    rows = []
    for rid in row_ids:
        row_block = blocks.get(rid, {}).get("value", {})
        if not row_block:
            continue
        props = row_block.get("properties", {})
        if col_order:
            cells = [_cell_text(props.get(col, [[""]])) for col in col_order]
        else:
            cells = [_cell_text(v) for v in props.values()]
        rows.append(cells)

    if not rows:
        return []

    lines = []
    lines.append("| " + " | ".join(rows[0]) + " |")
    lines.append("| " + " | ".join(["---"] * len(rows[0])) + " |")
    for row in rows[1:]:
        while len(row) < len(rows[0]):
            row.append("")
        lines.append("| " + " | ".join(row) + " |")
    return lines


def _prefetch_sub_pages(blocks: dict, root_id: str, visited: set) -> set:
    """Pre-fetch all direct sub-pages in parallel before rendering.
    Populates `blocks` in-place and returns the set of successfully fetched IDs.
    The renderer uses this set to skip redundant sequential fetch calls.
    """
    root_content = blocks.get(root_id, {}).get("value", {}).get("content", [])
    to_fetch = [
        bid for bid in root_content
        if blocks.get(bid, {}).get("value", {}).get("type") == "page"
        and bid != root_id
        and bid not in visited
    ]
    if not to_fetch:
        return set()
    # Collect results into a local dict per thread, then merge in the main thread.
    # dict.update() is not safe to call concurrently from multiple worker threads.
    thread_results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(len(to_fetch), 5)) as executor:
        futures = {executor.submit(_notion_load_page_chunk, bid): bid for bid in to_fetch}
        for future in as_completed(futures):
            bid = futures[future]
            try:
                sub_blocks = future.result()
            except Exception as e:
                print(f"[warn] Failed to prefetch sub-page {bid}: {e}", file=sys.stderr)
                continue
            if sub_blocks:
                thread_results[bid] = sub_blocks

    # Merge all results in the main thread
    prefetched = set()
    for bid, sub_blocks in thread_results.items():
        blocks.update(sub_blocks)
        prefetched.add(bid)
    return prefetched


def _resolve_notion_attachment_urls(image_blocks: list[tuple[str, str]]) -> dict[str, str]:
    """
    Batch-resolve Notion attachment references to signed CDN URLs.

    image_blocks: list of (block_id, attachment_ref) pairs
    Returns:      dict mapping attachment_ref -> signed CDN URL
    """
    if not image_blocks:
        return {}
    payload = {
        "urls": [
            {"url": att, "permissionRecord": {"table": "block", "id": bid}}
            for bid, att in image_blocks
        ]
    }
    try:
        resp = requests.post(
            "https://www.notion.so/api/v3/getSignedFileUrls",
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            json=payload,
            timeout=20,
        )
        if resp.status_code == 200:
            signed = resp.json().get("signedUrls", [])
            if len(signed) != len(image_blocks):
                print(
                    f"[warn] getSignedFileUrls returned {len(signed)} URLs for "
                    f"{len(image_blocks)} requested. Some attachment images may not resolve correctly.",
                    file=sys.stderr,
                )
            return {att: url for (_, att), url in zip(image_blocks, signed) if url}
    except Exception as e:
        print(f"[warn] Could not resolve signed image URLs: {e}", file=sys.stderr)
    return {}


def notion_blocks_to_markdown(blocks: dict, root_id: str) -> str:
    """Recursively render Notion blocks to markdown, fetching sub-pages on demand."""
    _visited: set = set()

    # Pre-fetch direct sub-pages in parallel to avoid sequential HTTP round-trips.
    # Returns the set of IDs that were successfully fetched — blocks dict is now populated for those.
    _prefetched = _prefetch_sub_pages(blocks, root_id, _visited)

    # Resolve all Notion attachment image references to signed CDN URLs in one batch call.
    _attachment_url_map: dict[str, str] = {}
    attachment_image_blocks = []
    for bid, b in blocks.items():
        val = b.get("value", {})
        if val.get("type") == "image":
            src = val.get("properties", {}).get("source", [[""]])[0][0]
            if src.startswith("attachment:"):
                attachment_image_blocks.append((bid, src))
    if attachment_image_blocks:
        _attachment_url_map = _resolve_notion_attachment_urls(attachment_image_blocks)

    def process(block_ids, depth=0):
        lines = []
        for block_idx, bid in enumerate(block_ids):
            b = blocks.get(bid, {}).get("value", {})
            if not b:
                continue
            btype = b.get("type", "")
            props = b.get("properties", {})
            text = get_notion_text(props)
            children = b.get("content", [])
            indent = "  " * depth

            # Sub-pages: fetch their content and inline it
            if btype == "page" and bid != root_id:
                if bid not in _visited:
                    _visited.add(bid)
                    # Skip network call only if this sub-page was already prefetched above.
                    # Can't rely on b.get("content") being truthy — Notion returns content IDs
                    # in the initial chunk but those blocks are NOT loaded until explicitly fetched.
                    if bid not in _prefetched:
                        sub_blocks = _notion_load_page_chunk(bid)
                        if sub_blocks:
                            blocks.update(sub_blocks)
                            b = blocks.get(bid, {}).get("value", {})
                    lines.append(f"\n## {text}\n")
                    lines.extend(process(b.get("content", []), depth))
                continue

            if btype == "header":
                lines.append(f"# {text}")
            elif btype == "sub_header":
                lines.append(f"## {text}")
            elif btype == "sub_sub_header":
                lines.append(f"### {text}")
            elif btype == "text":
                lines.append(f"{indent}{text}" if text else "")
            elif btype == "bulleted_list":
                lines.append(f"{indent}- {text}")
            elif btype == "numbered_list":
                preceding = sum(
                    1 for prev_bid in block_ids[:block_idx]
                    if blocks.get(prev_bid, {}).get("value", {}).get("type") == "numbered_list"
                )
                lines.append(f"{indent}{preceding + 1}. {text}")
            elif btype == "to_do":
                checked = props.get("checked", [[""]])[0][0] == "Yes"
                lines.append(f"{indent}- [x] {text}" if checked else f"{indent}- [ ] {text}")
            elif btype == "toggle":
                lines.append(f"{indent}> **{text}**")
                if children:
                    lines.extend(process(children, depth + 1))
            elif btype == "quote":
                lines.append(f"{indent}> {text}")
            elif btype == "callout":
                icon = b.get("format", {}).get("page_icon", "💡")
                lines.append(f"{indent}[callout:{icon}] {text}")
                if children:
                    lines.extend(process(children, depth + 1))
            elif btype == "divider":
                lines.append("---")
            elif btype == "code":
                lang = props.get("language", [["plain text"]])[0][0]
                lines.append(f"```{lang}\n{text}\n```")
            elif btype == "image":
                raw_src = props.get("source", [[""]])[0][0] if props.get("source") else ""
                # Resolve attachment: references to signed CDN URLs via getSignedFileUrls.
                # Fall back to the raw reference if resolution failed.
                src = _attachment_url_map.get(raw_src, raw_src)
                if src:
                    lines.append(f"[Image: {src}]")
            elif btype == "table":
                lines.extend(_render_notion_table(blocks, bid))
            elif btype == "table_row":
                pass  # handled by table renderer
            elif btype == "bookmark":
                link = props.get("link", [[""]])[0][0] if props.get("link") else ""
                lines.append(f"[{text}]({link})" if link else f"[{text}]")
            elif btype in ("column_list", "column"):
                if children:
                    lines.extend(process(children, depth))

            # Generic recursion for block types not explicitly handled above
            if children and btype not in (
                "toggle", "callout", "table", "table_row", "column_list", "column", "page"
            ):
                lines.extend(process(children, depth + 1))

        return lines

    root_block = blocks.get(root_id, {}).get("value", {})
    content_ids = root_block.get("content", [])
    lines = process(content_ids)
    return "\n".join(lines)


# ─── GOOGLE DOCS / DRIVE ───────────────────────────────────────────────────────

def fetch_google_doc(url: str) -> str:
    """Fetch a public Google Doc as plain text using the export URL."""
    # Extract document ID
    doc_id = None
    export_url = None

    # Google Docs: /document/d/{ID}/
    match = re.search(r'/document/d/([a-zA-Z0-9_-]+)', url)
    if match:
        doc_id = match.group(1)
        export_url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"

    # Google Drive: /file/d/{ID}/
    if not doc_id:
        match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
        if match:
            doc_id = match.group(1)
            export_url = f"https://drive.google.com/uc?export=download&id={doc_id}"

    if not doc_id:
        sys.exit(f"Could not extract document ID from Google URL: {url}")

    if _is_private_url(export_url):
        sys.exit(f"Blocked: export URL resolves to a private address: {export_url}")

    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(export_url, headers=headers, timeout=20, allow_redirects=True, stream=True)

    if resp.status_code != 200:
        sys.exit(f"Google export failed ({resp.status_code}). Make sure the document is set to 'Anyone with the link can view'.")

    chunks: list[bytes] = []
    total = 0
    for chunk in resp.iter_content(chunk_size=65536):
        total += len(chunk)
        if total > _MAX_RESPONSE_BYTES:
            sys.exit("Google Doc response too large (> 10 MB). Fetch aborted.")
        chunks.append(chunk)
    raw = b"".join(chunks)

    # Google Drive /file/d/ links often serve a raw PDF binary rather than plain text.
    # Detect by magic bytes and route through the PDF extractor instead of text decoding.
    if raw[:4] == b"%PDF":
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name
        print(f"[fetch] Google Drive file is a PDF — extracting text via pdfplumber", file=sys.stderr)
        return fetch_pdf(tmp_path)

    text = raw.decode(resp.encoding or "utf-8", errors="replace").strip()
    # Google silently redirects private/missing docs to an HTML error page (HTTP 200).
    # Detect this by checking for Google's error page markers in the response.
    if text.startswith("<!DOCTYPE") or "<html" in text[:200]:
        sys.exit("Google returned an HTML page instead of document text. Make sure the document is set to 'Anyone with the link can view'.")

    return text


# ─── PDF ───────────────────────────────────────────────────────────────────────

def fetch_pdf(path: str) -> str:
    """Extract text and embedded images from a PDF file."""
    try:
        import pdfplumber
    except ImportError:
        sys.exit("pdfplumber not installed. Run: pip install pdfplumber")

    if not Path(path).exists():
        sys.exit(f"PDF not found: {path}")

    text_parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)

    if not text_parts:
        sys.exit("No text extracted from PDF. It may be image-based (scanned). Try copying text manually.")

    # Also extract embedded images using PyMuPDF (already a project dependency).
    # Images are saved to output/extracted_images/ and referenced as [Image: path].
    # Path is resolved relative to this script file, not the process CWD.
    try:
        import fitz  # PyMuPDF
        images_dir = Path(__file__).parent.parent / "output" / "extracted_images"
        images_dir.mkdir(parents=True, exist_ok=True)
        image_paths = []

        with fitz.open(path) as doc:
            # Collect all qualifying images first, then cap at 20 (largest first)
            all_images = []
            for page_num, page in enumerate(doc):
                for img_idx, img_info in enumerate(page.get_images(full=True)):
                    xref = img_info[0]
                    base_img = doc.extract_image(xref)
                    img_bytes = base_img["image"]
                    img_ext = base_img["ext"]
                    # Skip tiny images (icons, bullets) under 5 KB
                    if len(img_bytes) < 5_120:
                        continue
                    all_images.append((page_num, img_idx, img_bytes, img_ext))

            # Sort by size descending, cap at 20 to avoid flooding context
            all_images.sort(key=lambda x: len(x[2]), reverse=True)
            if len(all_images) > 20:
                print(f"[info] PDF has {len(all_images)} images; extracting top 20 by size", file=sys.stderr)
            for page_num, img_idx, img_bytes, img_ext in all_images[:20]:
                img_path = images_dir / f"pdf_p{page_num + 1}_img{img_idx + 1}.{img_ext}"
                img_path.write_bytes(img_bytes)
                image_paths.append(str(img_path))

        if image_paths:
            text_parts.append(
                "--- Images extracted from PDF ---\n"
                + "\n".join(f"[Image: {p}]" for p in image_paths)
            )
    except Exception as e:
        print(f"[warn] PDF image extraction skipped: {e}", file=sys.stderr)

    return "\n\n".join(text_parts)


# ─── GENERIC URL ──────────────────────────────────────────────────────────────

# Minimum character count for static fetch to be considered adequate.
# Pages returning less than this are assumed to be JS-rendered SPAs.
_SPARSE_CONTENT_THRESHOLD = 300


def _extract_images_from_soup(soup, main) -> list[str]:
    """Return a deduplicated list of absolute image URLs found in the page."""
    imgs = main.find_all("img") if main else soup.find_all("img")
    image_urls: list[str] = []
    seen_urls: set[str] = set()
    for img in imgs:
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
        src = src.strip()
        if (
            src.startswith("http")
            and any(src.lower().split("?")[0].endswith(ext) for ext in _IMAGE_EXTS)
            and src not in seen_urls
        ):
            image_urls.append(src)
            seen_urls.add(src)
    return image_urls[:20]


def _fetch_url_playwright(url: str) -> str:
    """Render a JavaScript-heavy page with Playwright and return readable text.

    Returns an empty string if Playwright is unavailable or the render fails.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        print("[fetch] Playwright not available — skipping JS render", file=sys.stderr)
        return ""

    print("[fetch] Launching Playwright for JS render...", file=sys.stderr)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            try:
                page.goto(url, wait_until="networkidle", timeout=30_000)
            except PlaywrightTimeout:
                # networkidle can time out on pages that keep polling; fall back
                # to domcontentloaded and give JS a moment to settle.
                print("[fetch] networkidle timed out — falling back to domcontentloaded", file=sys.stderr)
                page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                page.wait_for_timeout(3_000)

            # Let any remaining async rendering settle
            page.wait_for_timeout(1_500)

            # Strip chrome/boilerplate from the live DOM before reading text
            page.evaluate("""
                document.querySelectorAll(
                    'script, style, noscript, nav, footer, header, aside, iframe, [aria-hidden="true"]'
                ).forEach(el => el.remove());
            """)

            text = page.inner_text("body") or ""

            # Collect visible image sources
            image_urls: list[str] = page.evaluate("""
                Array.from(document.querySelectorAll('img'))
                    .map(img => (img.getAttribute('src') || img.getAttribute('data-src') || '').trim())
                    .filter(src =>
                        src.startsWith('http') &&
                        /\\.(jpg|jpeg|png|gif|webp)(\\?|$)/i.test(src)
                    )
                    .slice(0, 20)
            """) or []

            cleaned_lines = [line.strip() for line in text.splitlines() if line.strip()]
            cleaned = "\n".join(cleaned_lines)

            if image_urls:
                cleaned += "\n\n--- Images found on page ---\n"
                cleaned += "\n".join(f"[Image: {u}]" for u in image_urls)

            return cleaned
        except Exception as exc:
            print(f"[fetch] Playwright render failed: {exc}", file=sys.stderr)
            return ""
        finally:
            browser.close()


def fetch_url(url: str) -> str:
    """Fetch any public URL and return readable text.

    First attempts a fast static fetch via requests + BeautifulSoup.
    If the result is sparse (JS-rendered SPA), falls back to Playwright.
    """
    from bs4 import BeautifulSoup

    if _is_private_url(url):
        sys.exit(f"Blocked: URL resolves to a private or loopback address: {url}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=20, stream=True)
    if resp.status_code != 200:
        sys.exit(f"Failed to fetch URL ({resp.status_code}): {url}")

    chunks: list[bytes] = []
    total = 0
    for chunk in resp.iter_content(chunk_size=65536):
        total += len(chunk)
        if total > _MAX_RESPONSE_BYTES:
            sys.exit(f"Response too large (> 10 MB), fetch aborted: {url}")
        chunks.append(chunk)
    html = b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")

    soup = BeautifulSoup(html, "html.parser")

    # Remove nav, footer, script, style
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
        tag.decompose()

    # Try to find main content area
    main = soup.find("main") or soup.find("article") or soup.find(id="content") or soup.body
    text = main.get_text(separator="\n", strip=True) if main else soup.get_text(separator="\n", strip=True)

    # Clean up excessive blank lines
    lines = [line.strip() for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line)

    # Append image references from static HTML
    image_urls = _extract_images_from_soup(soup, main)
    if image_urls:
        cleaned += "\n\n--- Images found on page ---\n"
        cleaned += "\n".join(f"[Image: {u}]" for u in image_urls)

    # If static content is too sparse the page is almost certainly JS-rendered.
    # Fall back to Playwright so the actual lead magnet content is captured.
    if len(cleaned.strip()) < _SPARSE_CONTENT_THRESHOLD:
        print(
            f"[fetch] Static content too sparse ({len(cleaned.strip())} chars) "
            "— retrying with Playwright JS renderer...",
            file=sys.stderr,
        )
        playwright_content = _fetch_url_playwright(url)
        if playwright_content and len(playwright_content.strip()) > len(cleaned.strip()):
            print(
                f"[fetch] Playwright render succeeded ({len(playwright_content.strip())} chars)",
                file=sys.stderr,
            )
            return playwright_content
        print("[fetch] Playwright render did not improve content — using static result", file=sys.stderr)

    return cleaned


# ─── ROUTER ───────────────────────────────────────────────────────────────────

def fetch(input_str: str, no_cache: bool = False) -> str:
    """Route to the correct fetcher based on input type."""
    s = input_str.strip()

    # PDF file path
    if s.lower().endswith(".pdf") or (not s.startswith("http") and Path(s).exists()):
        print("[fetch] Detected: PDF file", file=sys.stderr)
        return fetch_pdf(s)

    # Notion URL
    if "notion.so" in s or "notion.site" in s:
        print("[fetch] Detected: Notion page", file=sys.stderr)
        return fetch_notion(s, no_cache=no_cache)

    # Google Docs
    if "docs.google.com/document" in s:
        print("[fetch] Detected: Google Doc", file=sys.stderr)
        return fetch_google_doc(s)

    # Google Drive
    if "drive.google.com" in s or "docs.google.com/file" in s:
        print("[fetch] Detected: Google Drive file", file=sys.stderr)
        return fetch_google_doc(s)

    # Generic URL
    if s.startswith("http://") or s.startswith("https://"):
        print("[fetch] Detected: Generic URL", file=sys.stderr)
        return fetch_url(s)

    # Plain text — return as-is
    print("[fetch] Detected: Plain text input", file=sys.stderr)
    return s


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch content from any URL or file")
    parser.add_argument("--input", required=True, help="URL, file path, or raw text")
    parser.add_argument("--output", help="Optional: save to file instead of stdout")
    parser.add_argument("--no-cache", action="store_true", help="Bypass the 15-minute Notion page cache")

    args = parser.parse_args()
    content = fetch(args.input, no_cache=args.no_cache)

    if args.output:
        size = len(content.encode("utf-8"))
        if size == 0:
            sys.exit(f"ERROR: fetched content is empty — {args.input} may be private or empty")
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(content, encoding="utf-8")
        print(f"Saved to: {args.output} ({size:,} bytes)", file=sys.stderr)
    else:
        print(content)
