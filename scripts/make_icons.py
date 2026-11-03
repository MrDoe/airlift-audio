#!/usr/bin/env python3
"""Generate the Airlift Audio icon set (PNG + ICO). Needs Pillow.

    python scripts/make_icons.py

Writes airlift/assets/icon.png, icon_1024.png, icon.png sizes and icon.ico.
macOS .icns is produced in CI from the PNGs with `iconutil`.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "airlift" / "assets"
SIZE = 1024

BG_TOP = (15, 18, 24)
BG_BOTTOM = (27, 34, 44)
BORDER = (52, 62, 78)
ACCENT_DARK = (36, 128, 118)
ACCENT = (99, 210, 195)
ACCENT_LIGHT = (170, 255, 242)


def lerp(a, b, t: float):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def rounded_background() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # vertical gradient inside a rounded square
    radius = 220
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((24, 24, SIZE - 24, SIZE - 24),
                                           radius=radius, fill=255)
    gradient = Image.new("RGBA", (SIZE, SIZE))
    gdraw = ImageDraw.Draw(gradient)
    for y in range(SIZE):
        gdraw.line([(0, y), (SIZE, y)],
                   fill=lerp(BG_TOP, BG_BOTTOM, y / SIZE) + (255,))
    img.paste(gradient, (0, 0), mask)
    draw.rounded_rectangle((24, 24, SIZE - 24, SIZE - 24), radius=radius,
                           outline=BORDER, width=6)
    return img


def draw_waveform(img: Image.Image) -> None:
    draw = ImageDraw.Draw(img)
    heights = [0.20, 0.36, 0.55, 0.38, 0.68, 0.48, 0.82, 0.58, 0.94, 0.46, 0.28]
    bar_w, gap = 44, 26
    total = len(heights) * bar_w + (len(heights) - 1) * gap
    x = (SIZE - total) / 2
    base_y = SIZE / 2 + 70
    max_h = 560

    for value in heights:
        h = max_h * value
        top = base_y - h / 2
        bottom = base_y + h / 2
        # per-bar vertical gradient
        bar = Image.new("RGBA", (bar_w, int(h)), (0, 0, 0, 0))
        bdraw = ImageDraw.Draw(bar)
        for yy in range(int(h)):
            t = yy / max(1, h - 1)
            bdraw.line([(0, yy), (bar_w, yy)],
                       fill=lerp(ACCENT_DARK, ACCENT_LIGHT, t) + (255,))
        rounded = Image.new("L", (bar_w, int(h)), 0)
        ImageDraw.Draw(rounded).rounded_rectangle(
            (0, 0, bar_w - 1, int(h) - 1), radius=bar_w // 2, fill=255
        )
        img.paste(bar, (int(x), int(top)), rounded)
        x += bar_w + gap

    # "airlift" swoosh rising through the bars
    points = []
    for i in range(101):
        t = i / 100
        # quadratic bezier: bottom-left -> top-right
        px = 170 + (860 - 170) * t
        py = 790 - 500 * (t ** 1.35)
        points.append((px, py))
    draw.line(points, fill=ACCENT + (150,), width=10, joint="curve")
    draw.ellipse((points[-1][0] - 18, points[-1][1] - 18,
                  points[-1][0] + 18, points[-1][1] + 18),
                 fill=ACCENT_LIGHT + (235,))


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    img = rounded_background()
    draw_waveform(img)

    img.save(ASSETS / "icon_1024.png")
    img.resize((512, 512), Image.LANCZOS).save(ASSETS / "icon.png")
    for size in (256, 128, 64, 48, 32, 16):
        img.resize((size, size), Image.LANCZOS).save(ASSETS / f"icon_{size}.png")

    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ASSETS / "icon.ico", sizes=ico_sizes)
    print(f"icons written to {ASSETS}")


if __name__ == "__main__":
    main()
