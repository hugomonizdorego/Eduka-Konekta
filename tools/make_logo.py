#!/usr/bin/env python3
"""Generate the Eduka-Konekta logo files.

The mark is a speech bubble drawn as four coloured strokes joined by round
"connection" nodes: people (nodes) linked together through one school
conversation, with three typing dots inside.

The wordmark is set in Outfit SemiBold (SIL Open Font License) and converted
to vector outlines, so the logo renders identically without the font installed.

Usage:
    python3 tools/make_logo.py path/to/Outfit-SemiBold.(ttf|woff2)

Outputs (in assets/):
    eduka-konekta.svg            application icon (mark only)
    eduka-konekta-logo.svg       full logo, dark wordmark for light backgrounds
    eduka-konekta-logo-light.svg full logo, white wordmark for dark backgrounds
"""

from __future__ import annotations

import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"

PURPLE = "#866EFB"
TEAL = "#08CCB0"
PINK = "#FF476A"
YELLOW = "#F5CD00"
NAVY_NODE = "#05384A"
PLUM_NODE = "#831F67"
GREEN_NODE = "#09A600"
RED_NODE = "#ED1C24"
INK = "#222049"

# Bubble geometry (centre line). Stroke width 82, node radius 41.
W = 82
R = W / 2
CX = 953.0
LEFT, RIGHT = 656.0, 1249.5
TOP, BOTTOM = 645.0, 972.0
RADIUS = (BOTTOM - TOP) / 2
MIDY = TOP + RADIUS
INNER_L, INNER_R = LEFT + RADIUS, RIGHT - RADIUS
TAIL = (CX, 1055.0)


def mark(defs_id: str = "ek") -> tuple[str, str]:
    """Return (<defs>, <g>) for the bubble mark in its native coordinates."""
    stroke = f'fill="none" stroke-width="{W}" stroke-linejoin="round"'
    defs = (
        f'<clipPath id="{defs_id}-tail">'
        f'<rect x="{CX - R}" y="{BOTTOM}" width="{W}" height="{TAIL[1] - BOTTOM}"/>'
        f'<circle cx="{TAIL[0]}" cy="{TAIL[1]}" r="{R}"/></clipPath>'
    )
    yellow_path = f"M{RIGHT},{MIDY} A{RADIUS},{RADIUS} 0 0 1 {INNER_R},{BOTTOM} L{TAIL[0]},{TAIL[1]}"
    body = "".join([
        f'<path d="M{LEFT},{MIDY} A{RADIUS},{RADIUS} 0 0 1 {INNER_L},{TOP} L{CX},{TOP}" stroke="{PURPLE}" {stroke}/>',
        f'<path d="M{CX},{TOP} L{INNER_R},{TOP} A{RADIUS},{RADIUS} 0 0 1 {RIGHT},{MIDY}" stroke="{TEAL}" {stroke}/>',
        f'<path d="{yellow_path}" stroke="{YELLOW}" {stroke}/>',
        f'<path d="M{LEFT},{MIDY} A{RADIUS},{RADIUS} 0 0 0 {INNER_L},{BOTTOM} L{CX - 20},{BOTTOM} '
        f'Q{CX},{BOTTOM} {CX},{BOTTOM + 20} L{TAIL[0]},{TAIL[1]}" stroke="{PINK}" {stroke}/>',
        # Where the two strokes cross they mix to red, as in an overprint.
        f'<path d="{yellow_path}" stroke="{RED_NODE}" {stroke} clip-path="url(#{defs_id}-tail)"/>',
        f'<circle cx="{CX}" cy="{TOP}" r="{R}" fill="{NAVY_NODE}"/>',
        f'<circle cx="{LEFT + R}" cy="{MIDY + 7}" r="{R}" fill="{PLUM_NODE}"/>',
        f'<circle cx="{RIGHT - R}" cy="{MIDY + 7}" r="{R}" fill="{GREEN_NODE}"/>',
        f'<circle cx="{TAIL[0]}" cy="{TAIL[1]}" r="{R}" fill="{RED_NODE}"/>',
        f'<circle cx="828" cy="{MIDY}" r="22.5" fill="{PINK}"/>',
        f'<circle cx="955" cy="{MIDY}" r="22.5" fill="{TEAL}"/>',
        f'<circle cx="1082" cy="{MIDY}" r="22.5" fill="{YELLOW}"/>',
    ])
    return defs, body


MARK_BOX = (LEFT - R, TOP - R, RIGHT + R, TAIL[1] + R)  # x0, y0, x1, y1


def text_path(font: TTFont, text: str, size: float, x_center: float, baseline: float, tracking: float = 0.0) -> tuple[str, float]:
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    scale = size / font["head"].unitsPerEm
    names = [cmap[ord(char)] for char in text]
    advance = sum(hmtx[name][0] for name in names) * scale + tracking * (len(names) - 1)
    x = x_center - advance / 2
    pen = SVGPathPen(glyph_set)
    for name in names:
        glyph_set[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
        x += hmtx[name][0] * scale + tracking
    return pen.getCommands(), advance


def write_icon() -> None:
    defs, body = mark("icon")
    x0, y0, x1, y1 = MARK_BOX
    size = max(x1 - x0, y1 - y0) + 60
    vx = (x0 + x1) / 2 - size / 2
    vy = (y0 + y1) / 2 - size / 2
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vx:.1f} {vy:.1f} {size:.1f} {size:.1f}" '
        f'width="512" height="512"><title>Eduka-Konekta</title><defs>{defs}</defs>{body}</svg>\n'
    )
    (ASSETS / "eduka-konekta.svg").write_text(svg, encoding="utf-8")


def write_logo(font: TTFont, colour: str, filename: str) -> None:
    defs, body = mark("logo")
    word, width = text_path(font, "Eduka-Konekta", 250, CX, 1365, tracking=-2)
    tag, _ = text_path(font, "EDUKASAUN OS", 64, CX, 1475, tracking=14)
    margin = 90
    x0 = min(MARK_BOX[0], CX - width / 2) - margin
    x1 = max(MARK_BOX[2], CX + width / 2) + margin
    y0 = MARK_BOX[1] - margin
    y1 = 1475 + margin
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.1f} {y0:.1f} {x1 - x0:.1f} {y1 - y0:.1f}" '
        f'width="{(x1 - x0) / 2:.0f}" height="{(y1 - y0) / 2:.0f}"><title>Eduka-Konekta — Edukasaun OS</title>'
        f'<defs>{defs}</defs>{body}'
        f'<path d="{word}" fill="{colour}"/>'
        f'<path d="{tag}" fill="{TEAL if colour == INK else "#FFFFFF"}" fill-opacity="{1 if colour == INK else 0.8}"/></svg>\n'
    )
    (ASSETS / filename).write_text(svg, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    font = TTFont(sys.argv[1])
    write_icon()
    write_logo(font, INK, "eduka-konekta-logo.svg")
    write_logo(font, "#FFFFFF", "eduka-konekta-logo-light.svg")
    print("Logo files written to", ASSETS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
