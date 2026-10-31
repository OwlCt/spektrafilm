"""Draw the Spektrafilm macOS icon: a film gate with a spectral frame.

Writes an Apple iconset (for iconutil) and a PNG used as the in-app window icon.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


# Wavelength-ish samples from violet through deep red.
_SPECTRUM = (
    (88, 28, 135),
    (70, 55, 200),
    (30, 110, 220),
    (20, 170, 160),
    (80, 180, 60),
    (230, 190, 40),
    (230, 120, 30),
    (200, 50, 40),
)


def _lerp(a: int, b: int, t: float) -> int:
    return int(round(a + (b - a) * t))


def _spectrum_color(t: float) -> tuple[int, int, int]:
    t = min(max(t, 0.0), 1.0)
    scaled = t * (len(_SPECTRUM) - 1)
    index = int(scaled)
    if index >= len(_SPECTRUM) - 1:
        return _SPECTRUM[-1]
    local = scaled - index
    left = _SPECTRUM[index]
    right = _SPECTRUM[index + 1]
    return tuple(_lerp(left[channel], right[channel], local) for channel in range(3))


def render_icon(size: int = 1024) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    radius = int(size * 0.22)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=(20, 16, 14, 255))

    margin = int(size * 0.07)
    draw.rounded_rectangle(
        (margin, margin, size - 1 - margin, size - 1 - margin),
        radius=int(size * 0.08),
        fill=(36, 28, 24, 255),
    )

    hole_w = int(size * 0.055)
    hole_h = int(size * 0.042)
    hole_r = max(2, int(size * 0.012))
    count = 8
    top = int(size * 0.16)
    bottom = int(size * 0.84)
    step = (bottom - top) / (count - 1)
    for side in (int(size * 0.095), int(size * 0.905) - hole_w):
        for index in range(count):
            y = int(top + index * step - hole_h / 2)
            draw.rounded_rectangle(
                (side, y, side + hole_w, y + hole_h),
                radius=hole_r,
                fill=(8, 7, 6, 255),
            )

    frame = (
        int(size * 0.22),
        int(size * 0.24),
        int(size * 0.78),
        int(size * 0.76),
    )
    border = max(2, int(size * 0.018))
    draw.rounded_rectangle(frame, radius=int(size * 0.03), fill=(232, 214, 186, 255))
    inner = (frame[0] + border, frame[1] + border, frame[2] - border, frame[3] - border)
    width = inner[2] - inner[0]
    height = inner[3] - inner[1]
    gradient = Image.new("RGBA", (width, height))
    pixels = gradient.load()
    for x in range(width):
        color = _spectrum_color(x / max(1, width - 1))
        for y in range(height):
            shade = 1.0 - 0.18 * (y / max(1, height - 1))
            pixels[x, y] = tuple(int(channel * shade) for channel in color) + (255,)
    # Orange mask along the bottom of the frame, like a color negative base.
    mask_h = max(1, int(height * 0.16))
    for y in range(height - mask_h, height):
        blend = (y - (height - mask_h)) / mask_h
        for x in range(width):
            src = pixels[x, y]
            orange = (196, 92, 32, 255)
            pixels[x, y] = tuple(
                int(src[channel] * (1 - 0.55 * blend) + orange[channel] * 0.55 * blend) for channel in range(3)
            ) + (255,)
    image.paste(gradient, (inner[0], inner[1]))
    return image


def write_iconset(iconset: Path, master: Image.Image) -> None:
    iconset.mkdir(parents=True, exist_ok=True)
    named_sizes = {
        "icon_16x16.png": 16,
        "icon_16x16@2x.png": 32,
        "icon_32x32.png": 32,
        "icon_32x32@2x.png": 64,
        "icon_128x128.png": 128,
        "icon_128x128@2x.png": 256,
        "icon_256x256.png": 256,
        "icon_256x256@2x.png": 512,
        "icon_512x512.png": 512,
        "icon_512x512@2x.png": 1024,
    }
    for name, size in named_sizes.items():
        master.resize((size, size), Image.Resampling.LANCZOS).save(iconset / name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iconset", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    args = parser.parse_args()
    master = render_icon(1024)
    args.png.parent.mkdir(parents=True, exist_ok=True)
    master.save(args.png)
    write_iconset(args.iconset, master)


if __name__ == "__main__":
    main()
