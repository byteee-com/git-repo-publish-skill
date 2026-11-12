#!/usr/bin/env python3
"""Generate outlined Simplified Chinese art from the English README assets."""

import argparse
from pathlib import Path
from xml.etree import ElementTree as ET

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont


SVG = "http://www.w3.org/2000/svg"
ART = Path(__file__).resolve().parent.parent
HERO = {
    "FIRST-PUBLISH PASS": "首次发布登机牌",
    "LOCAL": "本地",
    "GATE": "确认",
    "FROM": "源路径",
    "TO": "发布到",
    "ACCOUNT": "登录账号",
    "@you": "@你的账号",
    "OWNER": "仓库归属",
    "owner": "归属方",
    "VISIBILITY": "可见性",
    "PRIVATE": "私有",
    "PROTOCOL": "推送协议",
    "BRANCH": "分支",
    "COMMIT · FULL SHA, READ BACK AFTER PUSH": "提交 · 推送后核对完整 SHA",
    "DESTINATION": "目标仓库",
    "NOTHING IS PUSHED": "确认之前",
    "BEFORE YOU CONFIRM": "代码不会推送",
    "AWAITING": "等待",
    "CONFIRMATION": "发布确认",
}
WORKFLOW = {
    "ON YOUR MACHINE": "本地项目",
    "read-only until the gate": "确认前仅检查",
    "ON GITHUB": "在 GitHub 上",
    "after you confirm": "你确认后执行",
    "INSPECT": "检查",
    "accounts": "列出账号",
    "owners · inspect": "检查归属和仓库",
    "PREVIEW": "预览",
    "branch · full SHA": "分支 · 完整 SHA",
    "owner · visibility": "归属 · 可见性",
    "PUBLISH": "发布",
    "creates the": "创建",
    "target branch": "目标分支",
    "VERIFY": "核验",
    "reads repo +": "读回仓库",
    "SHA back": "和提交 SHA",
    "CONFIRM": "确认发布",
    "if interrupted": "发布中断时",
    "RESUME": "恢复发布",
    "same confirmed target": "沿用已确认的目标",
}
ARTWORK = {
    "hero": (
        HERO,
        "github-repo-publish · 首次发布登机牌",
        "从本地项目发布到 GitHub。核对登录账号、仓库归属、可见性、协议、分支和完整提交 SHA，再确认发布。",
    ),
    "workflow": (
        WORKFLOW,
        "发布流程 · 检查、预览、确认、发布、核验",
        "先在本地检查并预览，确认后发布到 GitHub，再核验仓库和提交 SHA。发布中断后可以恢复到原目标。",
    ),
}


def outline(label, original, font):
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    glyph_names = [cmap[ord(char)] for char in label]
    size = 145 if original.text == "LOCAL" else float(original.attrib["font-size"])
    scale = size / font["head"].unitsPerEm
    gap = min(float(original.get("letter-spacing", "0")), 2)
    widths = [glyphs[name].width * scale for name in glyph_names]
    total = sum(widths) + gap * (len(widths) - 1)
    anchor = original.get("text-anchor", "start")
    offset = {"start": 0, "middle": total / 2, "end": total}[anchor]
    x = float(original.attrib["x"]) - offset
    y = float(original.attrib["y"])
    pen = SVGPathPen(glyphs, ntos=lambda n: str(round(n, 2)))
    for name, width in zip(glyph_names, widths):
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, y)))
        x += width + gap
    return pen.getCommands()


def localize(kind, theme, fonts):
    translations, title, description = ARTWORK[kind]
    name = f"{kind}-{theme}.svg"
    svg = ET.parse(ART / name).getroot()
    source = ET.parse(ART / "src" / name).getroot()
    labels = [group for group in svg.iter(f"{{{SVG}}}g") if "aria-label" in group.attrib]
    text_nodes = list(source.iter(f"{{{SVG}}}text"))
    if [group.attrib["aria-label"] for group in labels] != [node.text for node in text_nodes]:
        raise ValueError(f"Outlined English labels differ from the source in {name}")

    for group, original in zip(labels, text_nodes):
        if original.text not in translations:
            continue
        label = translations[original.text]
        face = "regular" if original.attrib["class"].split()[0] == "mono" else "bold"
        path = group.find(f"{{{SVG}}}path")
        path.set("d", outline(label, original, fonts[face]))
        group.set("aria-label", label)

    svg.set("{http://www.w3.org/XML/1998/namespace}lang", "zh-CN")
    svg.find(f"{{{SVG}}}title").text = title
    svg.find(f"{{{SVG}}}desc").text = description
    return ET.tostring(svg, encoding="unicode") + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("font_directory", type=Path, help="Directory containing the Noto Sans SC OTF files")
    args = parser.parse_args()
    ET.register_namespace("", SVG)
    fonts = {
        face: TTFont(args.font_directory / f"NotoSansSC-{face.title()}.otf")
        for face in ("regular", "bold")
    }
    for kind in ARTWORK:
        for theme in ("light", "dark"):
            output = ART / f"{kind}-zh-CN-{theme}.svg"
            output.write_text(localize(kind, theme, fonts), encoding="utf-8")


if __name__ == "__main__":
    main()
