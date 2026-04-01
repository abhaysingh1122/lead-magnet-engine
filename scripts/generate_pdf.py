"""
generate_pdf.py
Converts a markdown file into a clean, branded Abhay Singh PDF.

Usage:
    python scripts/generate_pdf.py \
        --title "Title" \
        --type "Playbook" \
        --subtitle "Subtitle" \
        --content output/file.md \
        --output output/file.pdf
"""

import argparse
import html as _html
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from xhtml2pdf import pisa
except ImportError:
    sys.exit("xhtml2pdf not installed. Run: pip install xhtml2pdf")

try:
    import markdown
    from markdown.extensions.tables import TableExtension
    from markdown.extensions.fenced_code import FencedCodeExtension
except ImportError:
    sys.exit("markdown not installed. Run: pip install markdown")


TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "pdf-template.html"
ASSETS_DIR = Path(__file__).parent.parent / "assets"


def postprocess_pdf(pdf_path: str):
    """Post-process PDF via PyMuPDF to add centered watermark and running footer on every page.
    Watermark: Abhay Singh logo at 7% opacity, centered on each page.
    Footer: 'Abhay Singh • abhaysinghnagarkoti.work@gmail.com' left, page number right, with thin separator line.
    """
    try:
        import fitz
        from PIL import Image
        import io as _io
    except ImportError:
        print("[warn] PyMuPDF or Pillow not available — skipping watermark+footer", file=sys.stderr)
        return

    # Build low-opacity watermark PNG bytes
    wm_bytes = None
    wm_pts_w = wm_pts_h = 0.0
    for name in ("abhay-logo-converted.png", "abhay-logo.png"):
        logo_path = ASSETS_DIR / name
        if logo_path.exists():
            img = Image.open(logo_path).convert("RGBA")
            r, g, b, a = img.split()
            a = a.point(lambda x: int(x * 0.07))
            img.putalpha(a)
            buf = _io.BytesIO()
            img.save(buf, "PNG")
            buf.seek(0)
            wm_bytes = buf.read()
            # Target width: 110mm = 311.8pts
            scale = 311.8 / img.width
            wm_pts_w = 311.8
            wm_pts_h = img.height * scale
            break

    doc = fitz.open(pdf_path)
    tmp_path = pdf_path + ".tmp"
    saved = False
    try:
        for page_num, page in enumerate(doc):
            w, h = page.rect.width, page.rect.height
            left_margin = 70.9   # 25mm
            right_margin = w - 70.9

            # ── Watermark: centered, behind content ──────────────────────────────
            if wm_bytes:
                x0 = (w - wm_pts_w) / 2
                y0 = (h - wm_pts_h) / 2
                wm_rect = fitz.Rect(x0, y0, x0 + wm_pts_w, y0 + wm_pts_h)
                page.insert_image(wm_rect, stream=wm_bytes, overlay=False)

            # ── Footer: separator line + brand name (left) + page number (right) ─
            footer_y = h - 18.0   # 18pts from bottom edge (~6.3mm)
            line_y = footer_y - 5.0
            grey = (0.67, 0.67, 0.67)
            light = (0.82, 0.82, 0.82)

            shape = page.new_shape()
            shape.draw_line(fitz.Point(left_margin, line_y), fitz.Point(right_margin, line_y))
            shape.finish(color=light, width=0.5)
            shape.commit()

            page.insert_text(
                fitz.Point(left_margin, footer_y),
                "Abhay Singh  \u2022  abhaysinghnagarkoti.work@gmail.com",
                fontsize=7, color=grey,
            )
            page_label = str(page_num + 1)
            text_w = fitz.get_text_length(page_label, fontname="helv", fontsize=7)
            page.insert_text(
                fitz.Point(right_margin - text_w, footer_y),
                page_label,
                fontsize=7, color=grey,
            )

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


def load_template() -> str:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def preprocess_custom_syntax(text: str, images_dir: str | None = None) -> str:
    """Convert custom Abhay Singh markdown syntax to HTML before main markdown conversion."""
    import base64

    lines = text.split('\n')
    result = []

    for line in lines:
        # Strip em dashes (hard rule — never appear in any output)
        line = line.replace('\u2014', ' - ').replace('\u2013', '-')

        # [callout:emoji] Text
        callout_match = re.match(r'^\[callout:(.+?)\]\s*(.*)', line)
        if callout_match:
            emoji = callout_match.group(1).strip()
            content = callout_match.group(2).strip()
            if emoji in ('⚠️', '🚨'):
                bg, border = '#FFF8ED', '#F59E0B'
            elif emoji in ('💡', '✅'):
                bg, border = '#F0FDF4', '#10B981'
            else:
                bg, border = '#EBF4FF', '#3B82F6'
            # Convert markdown links inside callout
            content_html = re.sub(
                r'\[([^\]]+)\]\(([^)]+)\)',
                r'<a href="\2" style="color:#0056A7;">\1</a>',
                _html.escape(content)
            )
            result.append(
                f'<div style="background:{bg};border-left:3px solid {border};'
                f'padding:8px 14px;margin:5mm 0 3mm 0;border-radius:2px;">'
                f'<span style="margin-right:6px;">{emoji}</span>'
                f'<span style="font-size:10pt;line-height:1.55;">{content_html}</span></div>'
            )
            continue

        # [image:filename.png]
        image_match = re.match(r'^\[image:(.+?)\]', line)
        if image_match:
            filename = Path(image_match.group(1).strip()).name  # basename only — prevents path traversal
            img_path = None
            if images_dir:
                candidate = Path(images_dir) / filename
                if candidate.exists():
                    img_path = candidate
            if img_path:
                data = img_path.read_bytes()
                b64 = base64.b64encode(data).decode('ascii')
                ext = img_path.suffix.lstrip('.').lower()
                mime = 'image/png' if ext == 'png' else f'image/{ext}'
                result.append(
                    f'<div class="img-wrap">'
                    f'<img src="data:{mime};base64,{b64}" /></div>'
                )
            continue

        # - [ ] checkbox items
        checkbox_match = re.match(r'^(\s*)-\s*\[\s*\]\s*(.*)', line)
        if checkbox_match:
            indent = checkbox_match.group(1)
            content = checkbox_match.group(2)
            result.append(f'{indent}- \u25a1 {content}')
            continue

        result.append(line)

    return '\n'.join(result)


def md_to_html(text: str, images_dir: str | None = None) -> str:
    """Convert markdown to clean HTML using the proper markdown library."""
    text = preprocess_custom_syntax(text, images_dir=images_dir)
    md = markdown.Markdown(extensions=[
        TableExtension(),
        FencedCodeExtension(),
        "nl2br",
    ])
    return md.convert(text)


def strip_lead_title(text: str) -> str:
    """Remove the H1 title and H2 subtitle from content — they're already on the cover."""
    # Remove first H1
    text = re.sub(r'^#\s+[^\n]+\n', '', text.lstrip(), count=1)
    # Remove first H2 if it immediately follows
    text = re.sub(r'^\s*##\s+[^\n]+\n', '', text.lstrip(), count=1)
    return text.lstrip()


def wrap_cta_section(html: str) -> str:
    """Wrap the CTA H2 ('Want Help Running...') and everything after it in a styled blue box.
    Also fixes callout/link colors inside the CTA so they read on dark blue background.
    """
    m = re.search(r'<h2[^>]*>.*?want\s+help\s+running.*?</h2>', html, re.IGNORECASE | re.DOTALL)
    if not m:
        return html
    start = m.start()
    cta_content = html[start:]

    # Fix callout div colors to work on dark blue background
    cta_content = re.sub(
        r'<div style="background:[^;]+;border-left:[^;]+;(padding:[^;]+;margin:[^;]+;border-radius:[^;]+;)">'
        r'<span style="margin-right:6px;">(.*?)</span>'
        r'<span style="font-size:10pt;line-height:1.55;">(.*?)</span></div>',
        lambda mo: (
            f'<div style="background:#1863DC;border-left:3px solid #FFFFFF;{mo.group(1)}">'
            f'<span style="margin-right:6px;">{mo.group(2)}</span>'
            f'<span style="font-size:10pt;line-height:1.55;color:#FFFFFF;">{mo.group(3)}</span></div>'
        ),
        cta_content,
        flags=re.DOTALL
    )
    # Fix link colors inside CTA to white
    cta_content = re.sub(r'style="color:#0056A7;"', 'style="color:#FFFFFF;text-decoration:underline;"', cta_content)

    return (
        html[:start]
        + '<div class="cta-section">'
        + cta_content
        + '</div>'
    )


def fix_table_widths(html: str) -> str:
    """Set explicit width attributes on <th> elements in every table.
    xhtml2pdf ignores colgroup — direct width attrs on th are the only reliable fix.
    Also fills empty <th></th> cells with &nbsp; so xhtml2pdf doesn't collapse them.
    """
    def fix_one_table(m):
        table_html = m.group(0)
        # Locate the first <tr> that contains <th> elements
        header_match = re.search(r'(<tr[^>]*>)([ \t\n]*(?:<th[^>]*>.*?</th>[ \t\n]*)+)(</tr>)',
                                 table_html, re.DOTALL)
        if not header_match:
            return table_html
        header_cells_str = header_match.group(2)
        cells = re.findall(r'<th[^>]*>', header_cells_str)
        n = len(cells)
        if n == 0:
            return table_html
        w = round(100 / n, 1)

        # 1. Add width attribute to every <th>
        def add_width_to_th(cm):
            tag = cm.group(0)
            if 'width=' in tag:
                return tag
            return tag[:-1] + f' width="{w}%">'
        new_cells = re.sub(r'<th[^>]*>', add_width_to_th, header_cells_str)

        # 2. Replace empty <th ...></th> with <th ...>&nbsp;</th>
        new_cells = re.sub(r'(<th[^>]*>)\s*(</th>)', r'\1&nbsp;\2', new_cells)

        return (table_html[:header_match.start(2)]
                + new_cells
                + table_html[header_match.end(2):])

    return re.sub(r'<table.*?</table>', fix_one_table, html, flags=re.DOTALL)


def clean_for_pdf(html: str) -> str:
    """
    Replace unicode characters that xhtml2pdf/latin-1 can't handle.
    All replacements use safe ASCII or HTML entities.
    """
    subs = {
        "\u2014": " - ",      # em dash
        "\u2013": "-",         # en dash
        "\u2019": "'",         # right single quote
        "\u2018": "'",         # left single quote
        "\u201c": '"',         # left double quote
        "\u201d": '"',         # right double quote
        "\u2022": "&#8226;",  # bullet (html entity works in xhtml2pdf)
        "\u2192": "&#8594;",  # right arrow
        "\u2026": "...",       # ellipsis
        "\u00a0": " ",         # non-breaking space
        "\u2713": "&#10003;", # checkmark
        "\u00d7": "x",         # multiplication sign
        "\ufffd": "",          # replacement char (corrupted)
    }
    for char, rep in subs.items():
        html = html.replace(char, rep)
    # Strip any remaining characters that can't encode to latin-1
    # (they'd become '?' anyway — strip them cleanly instead)
    html = re.sub(r'[^\x00-\xFF]+', '', html)
    return html




def load_logo_b64() -> str:
    """Load the Abhay Singh logo as a base64 data string for embedding in HTML."""
    import base64
    # Prefer pre-encoded file if available
    for name in ("logo_b64.txt", "logo_b64_full.txt"):
        p = ASSETS_DIR / name
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    # Fall back: encode the PNG directly
    for name in ("abhay-logo-converted.png", "abhay-logo.png"):
        p = ASSETS_DIR / name
        if p.exists():
            return base64.b64encode(p.read_bytes()).decode("ascii")
    return ""


def generate_pdf(title: str, type_: str, subtitle: str, content_input: str, output_path: str, images_dir: str | None = None):
    template = load_template()

    # Read content
    if os.path.isfile(content_input):
        raw = Path(content_input).read_text(encoding="utf-8")
    else:
        raw = content_input

    # Strip leading H1/H2 (already shown in template header)
    raw = strip_lead_title(raw)

    # Convert markdown -> clean HTML (handles callouts, images, checkboxes)
    content_html = md_to_html(raw, images_dir=images_dir)

    # Fix table column widths
    content_html = fix_table_widths(content_html)

    # Wrap CTA section in styled blue box
    content_html = wrap_cta_section(content_html)

    # Build subtitle block (only if subtitle is non-empty)
    subtitle_clean = subtitle.strip()
    if subtitle_clean:
        subtitle_block = f'<p class="doc-subtitle">{_html.escape(subtitle_clean)}</p>'
    else:
        subtitle_block = ""

    # Load logo base64
    logo_b64 = load_logo_b64()

    # Inject into template
    date = datetime.now().strftime("%B %Y")
    html = (
        template
        .replace("{{title}}", _html.escape(title))
        .replace("{{subtitle_block}}", subtitle_block)
        .replace("{{logo_b64}}", logo_b64)
        .replace("{{content}}", content_html)
        .replace("{{date}}", date)
    )

    # Clean unicode for xhtml2pdf
    html = clean_for_pdf(html)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "wb") as f:
        result = pisa.CreatePDF(
            html.encode("latin-1", errors="replace"),
            dest=f
        )

    if result.err:
        print(f"[warn] {result.err} rendering note(s)", file=sys.stderr)

    if Path(output_path).stat().st_size == 0:
        sys.exit(f"ERROR: PDF not written to {output_path}")

    # Post-process: add centered watermark + running footer via PyMuPDF
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
