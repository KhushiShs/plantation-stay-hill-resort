#!/usr/bin/env python3
"""
Image optimization pipeline for Plantation Stay.
Reads source JPEG images from img_source/ and outputs responsive WebP images
at 3 standard viewport sizes (400w, 768w, 1200w) into app/static/img/.
Also computes dominant average background colors for layout stability (zero CLS).
"""
import os
import json
from pathlib import Path
from PIL import Image

SOURCE_DIR = Path("img_source")
OUTPUT_DIR = Path("app/static/img")
SIZES = [400, 768, 1200]
QUALITY = 82


def get_average_color(img: Image.Image) -> str:
    """Computes the average hex color of an image for background placeholders."""
    # Resize to 1x1 using Lanczos for exact weighted average
    rgb_img = img.convert("RGB")
    px = rgb_img.resize((1, 1), Image.Resampling.LANCZOS).getpixel((0, 0))
    return f"#{px[0]:02x}{px[1]:02x}{px[2]:02x}"


def process_images():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    metadata = {}

    source_files = sorted(SOURCE_DIR.glob("*.jpg"))
    if not source_files:
        print(f"No JPG source images found in {SOURCE_DIR}")
        return

    print(f"Found {len(source_files)} source images in {SOURCE_DIR}...")

    for src_path in source_files:
        stem = src_path.stem  # e.g. 'estate-hero', 'estate-room', 'luxury-villa'
        with Image.open(src_path) as im:
            orig_width, orig_height = im.size
            aspect_ratio = orig_width / orig_height
            avg_color = get_average_color(im)

            metadata[stem] = {
                "avg_color": avg_color,
                "orig_size": [orig_width, orig_height],
                "aspect_ratio": round(aspect_ratio, 4),
                "variants": {}
            }

            for width in SIZES:
                # Calculate height keeping aspect ratio
                height = int(round(width / aspect_ratio))
                resized = im.resize((width, height), Image.Resampling.LANCZOS)
                
                out_filename = f"{stem}-{width}.webp"
                out_path = OUTPUT_DIR / out_filename
                
                # Save as optimized webp
                resized.save(out_path, "WEBP", quality=QUALITY, method=6)
                
                file_size_kb = out_path.stat().st_size / 1024
                print(f"  Generated {out_path} ({width}x{height}, {file_size_kb:.1f} KB)")
                
                metadata[stem]["variants"][str(width)] = {
                    "file": f"/static/img/{out_filename}",
                    "width": width,
                    "height": height,
                    "size_kb": round(file_size_kb, 1)
                }

    # Save metadata JSON for easy template / helper access
    meta_path = OUTPUT_DIR / "manifest.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print(f"\nWrote image manifest to {meta_path}")


if __name__ == "__main__":
    process_images()
