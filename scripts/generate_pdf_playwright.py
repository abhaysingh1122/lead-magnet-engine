"""
generate_pdf_playwright.py
Generates a high-quality branded Abhay Singh PDF using Playwright (Chromium).
Produces Notion-quality rendering with full CSS support, Google Fonts,
and proper page-break handling.

After generating, applies centered watermark + running footer via PyMuPDF.

Usage:
    python scripts/generate_pdf_playwright.py \
        --title "Title" \
        --type "Playbook" \
        --subtitle "Optional subtitle" \
        --content output/file.md \
        --output output/file.pdf \
        --images-dir output
"""

import argparse
import base64
import html as _html
import io
import os
import re
import sys
from datetime import datetime
from pathlib import Path

TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "pdf-template-playwright.html"
ASSETS_DIR = Path(__file__).parent.parent / "assets"


# ── Shared helpers (adapted from generate_pdf.py) ─────────────────────────────

def load_logo_b64() -> str:
    for name in ("logo_b64.txt", "logo_b64_full.txt"):
        p = ASSETS_DIR / name
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    for name in ("abhay-logo-converted.png", "abhay-logo.png"):
        p = ASSETS_DIR / name
        if p.exists():
            return base64.b64encode(p.read_bytes()).decode("ascii")
    return ""


def preprocess_markdown(text: str, images_dir: str | None = None) -> str:
    """Convert custom Abhay Singh syntax to HTML. Returns raw HTML snippets
    mixed with markdown lines for further processing."""
    lines = text.split("\n")
    result = []

    for line in lines:
        # Strip em/en dashes (hard rule)
        line = line.replace("\u2014", " ").replace("\u2013", "-")

        # [callout:emoji] Text
        callout_match = re.match(r"^\[callout:(.+?)\]\s*(.*)", line)
        if callout_match:
            emoji = callout_match.group(1).strip()
            content = callout_match.group(2).strip()
            if emoji in ("⚠️", "🚨"):
                cls = "callout-warning"
            elif emoji in ("💡", "✅"):
                cls = "callout-success"
            else:
                cls = "callout-info"
            # Convert markdown links
            content_html = re.sub(
                r"\[([^\]]+)\]\(([^)]+)\)",
                r'<a href="\2">\1</a>',
                _html.escape(content),
            )
            result.append(
                f'<div class="{cls}">'
                f'<span class="callout-inner">'
                f'<span style="margin-right:7px">{emoji}</span>'
                f"{content_html}"
                f"</span></div>"
            )
            continue

        # [image:filename.png]
        image_match = re.match(r"^\[image:(.+?)\]", line)
        if image_match:
            # Use only the basename to prevent path traversal (e.g. ../../.env)
            filename = Path(image_match.group(1).strip()).name
            img_path = None
            if images_dir:
                candidate = Path(images_dir) / filename
                if candidate.exists():
                    img_path = candidate
            if img_path:
                data = img_path.read_bytes()
                b64 = base64.b64encode(data).decode("ascii")
                ext = img_path.suffix.lstrip(".").lower()
                mime = "image/png" if ext == "png" else f"image/{ext}"
                result.append(
                    f'<div class="img-wrap">'
                    f'<img src="data:{mime};base64,{b64}" />'
                    f"</div>"
                )
            continue

        # - [ ] checkbox items
        checkbox_match = re.match(r"^(\s*)-\s*\[\s*\]\s*(.*)", line)
        if checkbox_match:
            indent = checkbox_match.group(1)
            content = checkbox_match.group(2)
            result.append(f"{indent}- \u25a1 {content}")
            continue

        result.append(line)

    return "\n".join(result)


def md_to_html(text: str, images_dir: str | None = None) -> str:
    try:
        import markdown
        from markdown.extensions.tables import TableExtension
        from markdown.extensions.fenced_code import FencedCodeExtension
    except ImportError:
        sys.exit("markdown not installed. Run: pip install markdown")

    text = preprocess_markdown(text, images_dir=images_dir)
    md = markdown.Markdown(extensions=[TableExtension(), FencedCodeExtension(), "nl2br"])
    return md.convert(text)


def fix_table_widths(html: str) -> str:
    def fix_one_table(m):
        table_html = m.group(0)
        header_match = re.search(
            r"(<tr[^>]*>)([ \t\n]*(?:<th[^>]*>.*?</th>[ \t\n]*)+)(</tr>)",
            table_html, re.DOTALL
        )
        if not header_match:
            return table_html
        header_cells_str = header_match.group(2)
        cells = re.findall(r"<th[^>]*>", header_cells_str)
        n = len(cells)
        if n == 0:
            return table_html
        w = round(100 / n, 1)

        def add_width(cm):
            tag = cm.group(0)
            if "width=" in tag:
                return tag
            # Merge into existing style attribute if present, else add new one
            if 'style="' in tag:
                return tag.replace('style="', f'style="width:{w}%;', 1)
            return tag[:-1] + f' style="width:{w}%">'

        new_cells = re.sub(r"<th[^>]*>", add_width, header_cells_str)
        new_cells = re.sub(r"(<th[^>]*>)\s*(</th>)", r"\1&nbsp;\2", new_cells)
        return table_html[: header_match.start(2)] + new_cells + table_html[header_match.end(2) :]

    return re.sub(r"<table.*?</table>", fix_one_table, html, flags=re.DOTALL)


def wrap_cta_section(html: str) -> str:
    # Use [^<]* to stay within a single h2 tag — never cross tag boundaries
    m = re.search(r"<h2[^>]*>[^<]*want\s+help[^<]*</h2>", html, re.IGNORECASE)
    if not m:
        return html
    start = m.start()
    cta_content = html[start:]

    # Fix callout colors inside CTA
    cta_content = re.sub(
        r'<div class="callout-\w+">(.*?)</div>',
        lambda mo: (
            '<div class="callout-info">' + mo.group(1) + "</div>"
        ),
        cta_content,
        flags=re.DOTALL,
    )

    return html[:start] + '<div class="cta-section">' + cta_content + "</div>"


def strip_lead_title(text: str) -> str:
    text = re.sub(r"^#\s+[^\n]+\n", "", text.lstrip(), count=1)
    text = re.sub(r"^\s*##\s+[^\n]+\n", "", text.lstrip(), count=1)
    return text.lstrip()


# ── Postprocess: watermark + footer via PyMuPDF ───────────────────────────────

def postprocess_pdf(pdf_path: str):
    try:
        import fitz
    except ImportError:
        print("[warn] PyMuPDF not available — skipping footer", file=sys.stderr)
        return

    # 70.9pts = ~25mm, matches the left/right PDF margins
    FOOTER_MARGIN_PTS = 70.9

    doc = fitz.open(pdf_path)
    tmp_path = pdf_path + ".tmp"
    saved = False
    try:
        for page_num, page in enumerate(doc):
            w, h = page.rect.width, page.rect.height
            left_margin = FOOTER_MARGIN_PTS
            right_margin = w - FOOTER_MARGIN_PTS

            footer_y = h - 18.0
            line_y = footer_y - 5.0
            grey = (0.67, 0.67, 0.67)
            light = (0.82, 0.82, 0.82)

            shape = page.new_shape()
            shape.draw_line(fitz.Point(left_margin, line_y), fitz.Point(right_margin, line_y))
            shape.finish(color=light, width=0.5)
            shape.commit()

            page.insert_text(fitz.Point(left_margin, footer_y), "Abhay Singh  \u2022  abhaysinghnagarkoti.work@gmail.com", fontsize=7, color=grey)
            page_label = str(page_num + 1)
            text_w = fitz.get_text_length(page_label, fontname="helv", fontsize=7)
            page.insert_text(fitz.Point(right_margin - text_w, footer_y), page_label, fontsize=7, color=grey)

        doc.save(tmp_path)
        saved = True
    finally:
        doc.close()
        if not saved and os.path.exists(tmp_path):
            os.remove(tmp_path)
    try:
        os.replace(tmp_path, pdf_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


# ── Main generator ─────────────────────────────────────────────────────────────

def generate_pdf(title: str, type_: str, subtitle: str, content_input: str, output_path: str, images_dir: str | None = None):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright not installed. Run: pip install playwright && playwright install chromium")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    # Read content
    if os.path.isfile(content_input):
        raw = Path(content_input).read_text(encoding="utf-8")
    else:
        raw = content_input

    raw = strip_lead_title(raw)

    # Convert markdown to HTML
    content_html = md_to_html(raw, images_dir=images_dir)
    content_html = fix_table_widths(content_html)
    content_html = wrap_cta_section(content_html)

    # Subtitle block
    subtitle_clean = subtitle.strip()
    subtitle_block = (
        f'<p class="cover-subtitle">{_html.escape(subtitle_clean)}</p>'
        if subtitle_clean else ""
    )

    logo_b64 = load_logo_b64()

    html = (
        template
        .replace("{{title}}", _html.escape(title))
        .replace("{{subtitle_block}}", subtitle_block)
        .replace("{{logo_b64}}", logo_b64)
        .replace("{{content}}", content_html)
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load", timeout=15000)
            page.pdf(
                path=output_path,
                format="A4",
                print_background=True,
                margin={"top": "0mm", "right": "0mm", "bottom": "0mm", "left": "0mm"},
            )
        finally:
            browser.close()

    if not Path(output_path).exists() or Path(output_path).stat().st_size == 0:
        sys.exit(f"ERROR: PDF not written to {output_path}")

    # Post-process: watermark + footer
    postprocess_pdf(output_path)

    print(f"SUCCESS: {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--type", default="Playbook")
    parser.add_argument("--subtitle", default="")
    parser.add_argument("--content", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--images-dir", default=None)
    args = parser.parse_args()
    generate_pdf(args.title, args.type, args.subtitle, args.content, args.output, images_dir=args.images_dir)
