#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "icons"
SS = 4


def flask(draw: ImageDraw.ImageDraw, cx: float, cy: float, scale: float, color: tuple[int, int, int, int], width: int) -> None:
    neck_top = cy - 190 * scale
    neck_bottom = cy - 95 * scale
    body_bottom = cy + 175 * scale
    half_neck = 52 * scale
    half_body = 150 * scale
    points = [
        (cx - half_neck, neck_top), (cx + half_neck, neck_top),
        (cx + half_neck, neck_bottom), (cx + half_body, body_bottom - 35 * scale),
        (cx + half_body - 20 * scale, body_bottom), (cx - half_body + 20 * scale, body_bottom),
        (cx - half_body, body_bottom - 35 * scale), (cx - half_neck, neck_bottom),
        (cx - half_neck, neck_top),
    ]
    draw.line(points, fill=color, width=width, joint="curve")
    draw.line([(cx - 85 * scale, neck_top), (cx + 85 * scale, neck_top)], fill=color, width=width)
    draw.ellipse([cx - 62 * scale, cy + 62 * scale, cx + 62 * scale, cy + 168 * scale], fill=(212, 167, 44, 235))
    draw.ellipse([cx - 26 * scale, cy + 10 * scale, cx + 12 * scale, cy + 48 * scale], fill=(231, 111, 81, 245))
    draw.ellipse([cx + 55 * scale, cy + 34 * scale, cx + 79 * scale, cy + 58 * scale], fill=(247, 244, 236, 235))


def icon(size: int, maskable: bool = False) -> Image.Image:
    canvas = size * SS
    img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = int(canvas * (0.14 if maskable else 0.05))
    radius = int(canvas * (0.24 if maskable else 0.23))
    draw.rounded_rectangle([pad, pad, canvas - pad, canvas - pad], radius=radius, fill=(13, 59, 62, 255))
    draw.ellipse([canvas * 0.62, canvas * 0.12, canvas * 0.95, canvas * 0.45], fill=(15, 118, 110, 80))
    draw.ellipse([canvas * 0.02, canvas * 0.62, canvas * 0.34, canvas * 0.94], fill=(198, 93, 67, 45))
    scale = canvas / 1024 * (0.78 if maskable else 0.92)
    flask(draw, canvas / 2, canvas * 0.49, scale, (247, 244, 236, 255), max(6, int(canvas * 0.026)))
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    icon(192).save(OUT / "icon-192.png")
    icon(512).save(OUT / "icon-512.png")
    icon(512, maskable=True).save(OUT / "maskable-512.png")
    print(f"wrote icons to {OUT}")


if __name__ == "__main__":
    main()
