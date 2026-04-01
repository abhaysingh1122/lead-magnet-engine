"""
generate_infographic.py
Generates a single infographic image using the Google Gemini Imagen 4 API.

Replaces the nano-banana MCP plugin dependency so the system works without
any private Claude Code plugins.

Usage:
    python scripts/generate_infographic.py \
        --prompt "A standalone infographic in neuro neo brutalism design style..." \
        --output "output/infographic-1-framework.png" \
        --aspect-ratio "1:1"

Requires GEMINI_API_KEY in .env (or as an environment variable).
"""

import argparse
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass


def generate(prompt: str, output_path: str, aspect_ratio: str = "1:1") -> str:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        sys.exit("google-genai not installed. Run: pip install google-genai")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY not set. Add it to your .env file.")

    client = genai.Client(api_key=api_key)

    # Try Gemini native image generation first (works on billing-enabled keys),
    # fall back to Imagen 4 if unavailable.
    image_bytes = None

    # Attempt 1: Gemini 2.5 Flash Image (native image gen, works with most keys)
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                import base64
                image_bytes = part.inline_data.data
                if isinstance(image_bytes, str):
                    image_bytes = base64.b64decode(image_bytes)
                break
    except Exception as e:
        print(f"Gemini 2.5 Flash Image failed ({e}), trying Imagen 4...", file=sys.stderr)

    # Attempt 2: Imagen 4 (requires paid plan)
    if not image_bytes:
        try:
            response = client.models.generate_images(
                model="imagen-4.0-generate-001",
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio=aspect_ratio,
                    output_mime_type="image/png",
                ),
            )
            if response.generated_images:
                image_bytes = response.generated_images[0].image.image_bytes
        except Exception as e:
            sys.exit(f"Both Gemini 2.5 Flash Image and Imagen 4 failed. Last error: {e}")

    if not image_bytes:
        sys.exit("No image returned. The prompt may have been blocked by safety filters.")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(image_bytes)

    if not out.exists() or out.stat().st_size == 0:
        sys.exit(f"ERROR: Image not written to {output_path}")

    print(f"SUCCESS: {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate an infographic via Gemini Imagen")
    parser.add_argument("--prompt", required=True, help="Full image generation prompt")
    parser.add_argument("--output", required=True, help="Output file path (e.g. output/infographic-1.png)")
    parser.add_argument("--aspect-ratio", default="1:1", help="Aspect ratio: 1:1, 16:9, 9:16, 4:3, 3:4 (default: 1:1)")
    args = parser.parse_args()
    generate(args.prompt, args.output, args.aspect_ratio)
