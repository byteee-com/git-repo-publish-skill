#!/usr/bin/env python3
"""Generate the bilingual README covers as outlined, static SVGs."""

import argparse
from html import escape
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont


THEMES = {
    "light": {
        "canvas": "#F6F0E4", "card": "#FFFCF6", "edge": "#C7B9A5",
        "ink": "#251E18", "muted": "#61554A", "accent": "#963C21", "status": "#F3E2D7",
    },
    "dark": {
        "canvas": "#141E30", "card": "#101929", "edge": "#384960",
        "ink": "#FAEFE0", "muted": "#A9B8CC", "accent": "#FFC186", "status": "#372B2B",
    },
}

COPY = {
    "en": {
        "headline": ("First", "publish"), "preview": "PUBLISH PREVIEW", "pending": "AWAITING CONFIRMATION",
        "headline_sizes": (100, 106),
        "visibility": "VISIBILITY", "private": "Private", "protocol": "PROTOCOL",
        "title": "git-repo-publish shows a preview before the first push",
        "description": "Example preview for owner/repo with private visibility and SSH, awaiting confirmation.",
    },
    "zh-CN": {
        "headline": ("首次", "发布"), "preview": "发布预览", "pending": "等待确认",
        "headline_sizes": (92, 92),
        "visibility": "可见性", "private": "私有", "protocol": "推送协议",
        "title": "git-repo-publish 在首次推送前展示预览",
        "description": "示例目标为 owner/repo，仓库为私有，推送协议为 SSH，当前正在等待确认。",
    },
}


def number(value):
    return f"{value:.2f}".rstrip("0").rstrip(".")


class OutlineFont:
    def __init__(self, path, **location):
        self.font = TTFont(path)
        self.glyphs = self.font.getGlyphSet(location=location)
        self.names = self.font.getBestCmap()
        self.units = self.font["head"].unitsPerEm

    def width(self, value, size):
        return sum(self.glyphs[self.names[ord(char)]].width for char in value) * size / self.units

    def label(self, value, x, y, size, fill):
        names = [self.names[ord(char)] for char in value]
        scale = size / self.units
        outline = SVGPathPen(self.glyphs, ntos=number)
        for name in names:
            glyph = self.glyphs[name]
            glyph.draw(TransformPen(outline, (scale, 0, 0, -scale, x, y)))
            x += glyph.width * scale
        return f'<path aria-label="{escape(value)}" fill="{fill}" d="{outline.getCommands()}"/>'


def cover(theme, copy, label, mono, *, dark):
    canvas, card, edge = (theme[key] for key in ("canvas", "card", "edge"))
    ink, muted, accent, status = (theme[key] for key in ("ink", "muted", "accent", "status"))
    first, second = copy["headline"]
    first_size, second_size = copy["headline_sizes"]
    pending = copy["pending"]
    status_width = label.width(pending, 22) + 48
    status_x = 1128 - status_width
    elements = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1180" height="312" viewBox="0 0 1180 312" role="img" aria-labelledby="title description">',
        f'<title id="title">{escape(copy["title"])}</title>',
        f'<desc id="description">{escape(copy["description"])}</desc>',
        f'<rect x="1" y="1" width="1178" height="310" rx="18" fill="{canvas}" stroke="{edge}" stroke-width="2"/>',
        f'<rect x="526" y="23" width="630" height="266" rx="9" fill="{card}" stroke="{edge}" stroke-width="2"/>',
        label.label(first, 48, 108, first_size, ink),
        label.label(second, 48, 208, second_size, ink),
    ]
    if dark:
        ticks = "".join(f"M{x} 274v7" for x in range(58, 505, 15))
        elements.append(f'<path d="{ticks}" fill="none" stroke="{edge}" stroke-width="2"/>')
    elements.extend([
        f'<path d="M55 253h300" fill="none" stroke="{ink}" stroke-width="3"/>',
        f'<path d="M392 253h134" fill="none" stroke="{edge}" stroke-width="3" stroke-dasharray="7 7"/>',
        f'<path d="M369 237v32m10-32v32" fill="none" stroke="{accent}" stroke-width="4"/>',
        f'<circle cx="64" cy="253" r="7" fill="{canvas}" stroke="{ink}" stroke-width="3"/>',
        f'<circle cx="207" cy="253" r="7" fill="{canvas}" stroke="{ink}" stroke-width="3"/>',
        label.label(copy["preview"], 557, 70, 23, muted),
        f'<rect x="{number(status_x)}" y="41" width="{number(status_width)}" height="40" rx="5" fill="{status}"/>',
        f'<circle cx="{number(status_x + 15)}" cy="61" r="4" fill="{accent}"/>',
        label.label(pending, status_x + 31, 69, 22, accent),
        mono.label("owner/repo", 553, 161, 69, ink),
        f'<path d="M556 186h570M836 206v57" fill="none" stroke="{edge}" stroke-width="2"/>',
        label.label(copy["visibility"], 557, 225, 21, muted),
        label.label(copy["private"], 556, 262, 31, ink),
        label.label(copy["protocol"], 865, 225, 21, muted),
        mono.label("SSH", 865, 262, 30, ink),
        "</svg>",
    ])
    return "\n".join(elements) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fonts", type=Path, help="Directory containing the three variable fonts listed in DESIGN.md.")
    args = parser.parse_args()
    output = Path(__file__).resolve().parents[1]
    latin = OutlineFont(args.fonts / "BricolageGrotesque.ttf", wght=800)
    mono = OutlineFont(args.fonts / "JetBrainsMono.ttf", wght=600)
    chinese = OutlineFont(args.fonts / "NotoSansSC.ttf", wght=750)
    for language, font in (("en", latin), ("zh-CN", chinese)):
        directory = output / language
        directory.mkdir(exist_ok=True)
        for mode, theme in THEMES.items():
            svg = cover(theme, COPY[language], font, mono, dark=mode == "dark")
            (directory / f"publish-preview-{mode}.svg").write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
