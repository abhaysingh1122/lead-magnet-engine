# Lead Magnet Generation In A Box

A Claude Code system that takes any existing lead magnet and transforms it into a polished, brand-consistent version — complete with AI-generated infographics, styled HTML, PDF, Word doc, and Notion page.

Drop in a URL, a PDF, or pasted text. Get back a fully enhanced lead magnet in minutes.

---

## What It Does

- Audits the original content silently (keep / cut / add) with no approval gate
- Rewrites everything from scratch in your brand voice — zero verbatim content from the original
- Injects your frameworks, benchmarks, and proof points throughout
- Generates 2-3 custom infographics (Gemini 2.5 Flash Image, falls back to Imagen 4)
- Runs a strict quality check on every infographic before including it
- Optionally generates a styled self-contained HTML version
- Exports a styled PDF (Playwright/Chromium with Google Fonts) and Word document
- Pushes the finished page directly to Notion with embedded images

---

## Prerequisites

- [Claude Code](https://claude.ai/download) installed and logged in
- Python 3.11+
- A Chromium-compatible browser (installed automatically via Playwright)
- API keys for: Notion, Gemini (all free tiers work)

---

## Installation

**1. Clone the repo**

```bash
git clone https://github.com/your-username/lead-magnet-generation-in-a-box.git
cd lead-magnet-generation-in-a-box
```

**2. Install Python dependencies**

```bash
pip install -r requirements.txt
playwright install chromium
```

**3. Set up your API keys**

```bash
cp .env.example .env
```

Open `.env` and fill in:

| Key | Where to get it |
|---|---|
| `NOTION_API_KEY` | [notion.so/my-integrations](https://www.notion.so/my-integrations) |
| `NOTION_PARENT_PAGE_ID` | Copy from the URL of your target Notion page |
| `GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com/app/apikey) |

**4. Set up Notion**

- Create a Notion integration at [notion.so/my-integrations](https://www.notion.so/my-integrations)
- Give it "Insert content" permission
- Open the parent page where lead magnets should live, click the `...` menu, and add your integration under "Connections"
- Copy the page ID from the URL (the 32-char hex string at the end) into `NOTION_PARENT_PAGE_ID`

---

## Usage

Open Claude Code in this project directory and run:

```
/repurpose-lead-magnet
```

Claude will ask for your input. You can provide:
- A public Notion page URL (sub-pages are fetched and inlined automatically)
- A Google Docs URL (set to "Anyone with the link can view")
- A local PDF file path
- Pasted text

The system audits silently, then runs the full 4-stage enhancement engine: audit, remove, write, and rebrand. No approval gates between stages.

---

## How the Workflow Runs

```
STEP 1   Fetch input (YouTube, Notion, Google Docs, PDF, URL, or pasted text)
STEP 2   Detect lead magnet type + choose Notion icon
STEP 3   Load brand context
STEP 4   4-stage engine: AUDIT -> REMOVE -> WRITE -> REBRAND
STEP 5   Show full output in chat + write markdown to output/
STEP 5.5 Generate 2-3 infographics in parallel, quality-check each
STEP 6   Relevance check: em dashes, banned words, structure, image refs
STEP 6.5 Generate PDF + DOCX in parallel
STEP 7   Push to Notion with image uploads, verify count
STEP 8   Generate distribution assets (email sequence + social posts)
```

---

## Customizing the Brand

Open `brand/abhay-brand-context.md` and replace it with your own brand profile. This file controls:

- Company overview and ICP
- Tone of voice rules
- Proprietary frameworks to inject
- Proof points and benchmarks
- Brand colors
- Banned words and writing rules

The skill at `.claude/commands/repurpose-lead-magnet.md` reads this file on every run.

---

## What Gets Generated

| File | Description |
|---|---|
| `output/[slug]-abhay.md` | Full markdown (source of truth) |
| `output/[slug]-abhay.pdf` | Styled PDF with cover page and branded footer |
| `output/[slug]-abhay.docx` | Word document with styled callout blocks |
| `output/infographic-*.png` | 2-3 AI-generated neo-brutalist infographics |
| `output/[slug]-email-sequence.md` | 5-part email micro-lesson series |
| `output/[slug]-social-posts.md` | 3 LinkedIn posts + 1 Twitter/X thread |
| Notion page | Live page with all images embedded via Notion file upload API |

---

## Project Structure

```
.claude/commands/
  repurpose-lead-magnet.md      # The /repurpose-lead-magnet skill (core workflow)
assets/                         # Brand logo (replace with your own)
brand/
  abhay-brand-context.md        # Brand profile, tone, frameworks, proof points
scripts/
  fetch_content.py              # Fetches YouTube transcripts, Notion pages,
                                # Google Docs, PDFs, and generic URLs.
                                # Multi-source mode combines multiple inputs.
  generate_infographic.py       # Generates infographics: tries Gemini 2.5 Flash
                                # Image first, falls back to Imagen 4
  generate_pdf_playwright.py    # Renders PDF via Playwright/Chromium with
                                # Google Fonts, custom callout styles, and
                                # PyMuPDF footer post-processing
  generate_doc.py               # Generates Word document with styled blocks
  generate_email_sequence.py    # Splits lead magnet into 5-part email series
  generate_social_posts.py      # Extracts 3 LinkedIn posts + Twitter thread
  push_to_notion.py             # Pushes markdown + images to Notion using
                                # the file upload API (POST /v1/file_uploads)
templates/
  pdf-template-playwright.html  # PDF visual design (CSS @page margins, fonts)
  pdf-template.html             # xhtml2pdf fallback template
memory/                         # Claude's persistent memory (auto-managed)
output/                         # All generated files land here (gitignored)
```

---

## Infographic Quality Rules

Every infographic passes a strict quality check before it's included. Claude inspects each generated image for:

- Warm cream/beige background (not white or gray)
- Thick black borders and hard offset drop shadows on all cards
- No logo, URL, CTA badge, or branding elements
- All labels spelled correctly, no duplicates or phantom items
- No hex codes or markdown syntax rendered as visible text
- Correct number of elements (2-card or 3-card layouts only)

If any check fails, Claude regenerates with a simpler prompt. If it still fails after one retry, the infographic is dropped rather than including a low-quality one.

---

## PDF Technical Notes

- Margins are controlled by CSS `@page { margin: 20mm 26mm 22mm 26mm }` in the template. Do not pass margins via Playwright's `page.pdf()` — they conflict.
- Footer ("Abhay Singh • abhaysinghnagarkoti.work@gmail.com" + page number) is added by PyMuPDF post-processing, not Playwright.
- No watermark. Chromium produces opaque white PDF pages that make overlay watermarks invisible or conflicting. Clean output is correct.
- Google Fonts (Bricolage Grotesque, Bebas Neue) require internet access on first run. Subsequent runs use the browser cache.

---

## Notion Content Fetcher

`fetch_content.py` automatically handles Notion sub-pages. When a Notion page contains child page blocks, each sub-page is fetched via a separate API call and inlined at the correct position. One URL fetch gets the full document — no manual intervention needed.

Supported input types:
- Notion pages (public or integration-accessible)
- Google Docs (view-only link)
- Local PDF files (with image extraction)
- Generic URLs

---

## Troubleshooting

**"playwright not installed"** — run `playwright install chromium`

**"GEMINI_API_KEY not set"** — check your `.env` file

**Infographic generation fails** — Gemini 2.5 Flash Image is tried first. If it fails, Imagen 4 is used as fallback. If both fail, check that billing is enabled on your Google Cloud project.

**Notion push fails with 401** — make sure the integration is connected to the parent page (see Notion setup above)

**PDF has no fonts / looks wrong** — Playwright needs internet access to load Google Fonts on first run

**Notion page not found** — double-check `NOTION_PARENT_PAGE_ID`. It should be the 32-char hex string, not a URL

**Image count mismatch after Notion push** — check that all `[image:filename.png]` tags in the markdown are on their own lines with no other content on the same line

---

## License

MIT
