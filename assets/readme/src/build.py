#!/usr/bin/env python3
"""Generate boarding-pass hero + branch-line workflow (light/dark) as source SVGs with <text>."""
import random
import sys
from pathlib import Path
from fontTools.ttLib import TTFont

import os
FONTS = Path(os.environ.get("FONTS_DIR", "fonts"))  # Bebas Neue, Oswald, JetBrains Mono (OFL)
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

FMAP = {
    "disp": "BebasNeue-Regular.ttf",
    "head": "Oswald-Bold.ttf",
    "headm": "Oswald-Medium.ttf",
    "mono": "JBM-Regular.ttf",
    "monob": "JBM-Bold.ttf",
}
_cache = {}


def width(cls, text, size, ls=0.0):
    if cls not in _cache:
        _cache[cls] = TTFont(str(FONTS / FMAP[cls]))
    f = _cache[cls]
    cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
    w = 0.0
    for ch in text:
        g = cmap.get(ord(ch), ".notdef")
        w += hmtx[g][0] * size / upm + ls
    return w - ls


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def T(x, y, s, cls, size, fill, anchor="start", ls=0, extra=""):
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    l = f' letter-spacing="{ls}"' if ls else ""
    return f'<text class="{cls} {fill}" x="{x:.1f}" y="{y:.1f}" font-size="{size}"{a}{l}{extra}>{esc(s)}</text>'


THEMES = {
    "light": dict(
        paper="#F2ECDF", shadow="#1B1A17", ink="#1B1A17", muted="#6B6457", rule="#1B1A17",
        acc="#D4430F", hair="#CFC6B4", bar="#1B1A17", edge="none", board="#E7DFCE",
    ),
    "dark": dict(
        paper="#0F1828", shadow="#05080E", ink="#F1EADB", muted="#8D9AB0", rule="#2C3B57",
        acc="#FFB23F", hair="#24324B", bar="#F1EADB", edge="#2C3B57", board="#16223A",
    ),
}


def style(t, motion=""):
    return f"""<style>
.ink{{fill:{t['ink']}}} .muted{{fill:{t['muted']}}} .acc{{fill:{t['acc']}}} .paper{{fill:{t['paper']}}}{motion}
</style>"""


# Hero motion: plays once (~1.8s), animates only transform/opacity, and the
# un-animated state IS the final frame — so reduced-motion and clients that
# ignore CSS animation both see the complete static design.
HERO_MOTION = """
.mv-route{transform-box:fill-box;transform-origin:left center;animation:mv-draw .8s cubic-bezier(.4,0,.2,1) both}
.mv-node{animation:mv-in .2s ease-out both}
.mv-n1{animation-delay:.1s} .mv-n2{animation-delay:.45s}
.mv-gate{animation:mv-gate .45s ease-out .8s both}
.mv-stamp{transform-box:fill-box;transform-origin:center;animation:mv-stamp .5s cubic-bezier(.2,.8,.3,1.2) 1.25s both}
@keyframes mv-draw{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@keyframes mv-in{from{opacity:0}to{opacity:1}}
@keyframes mv-gate{0%{opacity:.2}60%{opacity:1}80%{opacity:.6}100%{opacity:1}}
@keyframes mv-stamp{0%{opacity:0;transform:scale(1.5)}60%{opacity:1;transform:scale(.96)}100%{opacity:1;transform:scale(1)}}
@media (prefers-reduced-motion:reduce){.mv-route,.mv-node,.mv-gate,.mv-stamp{animation:none}}"""


# --------------------------------------------------------------------------- HERO
def hero(mode):
    t = THEMES[mode]
    W, H = 1280, 600
    P = 954  # perforation x
    ticket = f"M24 24 H{P-36} A18 18 0 0 0 {P} 24 H1256 V576 H{P} A18 18 0 0 0 {P-36} 576 H24 Z"
    o = []
    o.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t d">')
    o.append('<title id="t">github-repo-publish — a boarding pass for your first publish</title>')
    o.append('<desc id="d">A boarding pass from a local project to owner/repo on GitHub. It lists the preview fields the skill shows before publishing: account, owner, visibility, protocol, branch and full commit SHA. The stub is stamped "awaiting confirmation" at the --confirm-target gate.</desc>')
    o.append(style(t, HERO_MOTION))
    # shadow + ticket
    if mode == "light":
        o.append(f'<path d="{ticket}" transform="translate(8 8)" fill="{t["shadow"]}"/>')
        o.append(f'<path d="{ticket}" fill="{t["paper"]}" stroke="{t["ink"]}" stroke-width="2"/>')
    else:
        o.append(f'<path d="{ticket}" fill="{t["paper"]}" stroke="{t["edge"]}" stroke-width="2"/>')
        # faint dot-matrix texture on the stub (night board)
        dots = []
        for yy in range(48, 560, 16):
            for xx in range(P + 16, 1250, 16):
                dots.append(f"M{xx} {yy}h1.6")
        o.append(f'<path d="{" ".join(dots)}" stroke="{t["hair"]}" stroke-width="1.6" stroke-linecap="round"/>')
    # perforation
    o.append(f'<line x1="{P-18}" y1="48" x2="{P-18}" y2="552" stroke="{t["muted"]}" stroke-width="2" stroke-dasharray="2 9" stroke-linecap="round"/>')

    L = 64
    R = P - 54  # right edge of main body = 900
    # header
    o.append(T(L, 86, "GITHUB-REPO-PUBLISH", "head", 36, "ink", ls=1.5))
    o.append(T(R, 84, "FIRST-PUBLISH PASS", "mono", 22, "muted", "end", ls=2))
    o.append(f'<rect x="{L}" y="104" width="{R-L}" height="3" fill="{t["rule"] if mode=="light" else t["ink"]}"/>')

    # big route LOCAL → GITHUB
    big = 160
    yb = 262
    wl = width("disp", "LOCAL", big, 2)
    wg = width("disp", "GITHUB", big, 2)
    o.append(T(L - 4, yb, "LOCAL", "disp", big, "ink", ls=2))
    o.append(T(R + 4, yb, "GITHUB", "disp", big, "ink", "end", ls=2))
    if mode == "dark":
        # split-flap seam through the big letters
        sy = yb - big * 0.36 - 2
        o.append(f'<rect x="{L-6}" y="{sy:.0f}" width="{wl+12:.0f}" height="5" fill="{t["paper"]}"/>')
        o.append(f'<rect x="{R-wg-8:.0f}" y="{sy:.0f}" width="{wg+16:.0f}" height="5" fill="{t["paper"]}"/>')
    # route line between the codes, with commits and a gate
    x1, x2 = L + wl + 22, R - wg - 22
    ly = yb - big * 0.36
    gx = (x1 + x2) / 2
    o.append(f'<line class="mv-route" x1="{x1:.0f}" y1="{ly:.0f}" x2="{gx-16:.0f}" y2="{ly:.0f}" stroke="{t["ink"]}" stroke-width="4"/>')
    o.append(f'<line x1="{gx+16:.0f}" y1="{ly:.0f}" x2="{x2-6:.0f}" y2="{ly:.0f}" stroke="{t["ink"]}" stroke-width="4" stroke-dasharray="10 8"/>')
    o.append(f'<path d="M{x2-14:.0f} {ly-11:.0f} L{x2+2:.0f} {ly:.0f} L{x2-14:.0f} {ly+11:.0f}" fill="none" stroke="{t["ink"]}" stroke-width="4"/>')
    for i, cx in enumerate((x1 + 6, (x1 + gx) / 2), 1):
        o.append(f'<circle class="mv-node mv-n{i}" cx="{cx:.0f}" cy="{ly:.0f}" r="9" fill="{t["paper"]}" stroke="{t["ink"]}" stroke-width="4"/>')
    # gate: two posts with an accent bar
    o.append('<g class="mv-gate">')
    o.append(f'<rect x="{gx-14:.0f}" y="{ly-34:.0f}" width="6" height="68" fill="{t["acc"]}"/>')
    o.append(f'<rect x="{gx+9:.0f}" y="{ly-34:.0f}" width="6" height="68" fill="{t["acc"]}"/>')
    o.append(T(gx, ly + 62, "GATE", "monob", 22, "acc", "middle", ls=3))
    o.append("</g>")

    # from / to
    o.append(T(L, 314, "FROM", "mono", 22, "muted", ls=2))
    o.append(T(L + 78, 314, "~/Code/project", "monob", 24, "ink"))
    wto = width("monob", "owner/repo", 24)
    o.append(T(R - wto - 14, 314, "TO", "mono", 22, "muted", "end", ls=2))
    o.append(T(R, 314, "owner/repo", "monob", 24, "ink", "end"))

    # field grid (real preview fields from SKILL.md)
    o.append(f'<line x1="{L}" y1="346" x2="{R}" y2="346" stroke="{t["hair"]}" stroke-width="2"/>')
    cols = [L, L + 214, L + 428, L + 642]
    rowA = [("ACCOUNT", "@you"), ("OWNER", "owner"), ("VISIBILITY", "PRIVATE"), ("PROTOCOL", "HTTPS")]
    for (k, v), x in zip(rowA, cols):
        o.append(T(x, 386, k, "mono", 22, "muted", ls=2))
        o.append(T(x, 424, v, "monob", 30, "ink"))
    for x in cols[1:]:
        o.append(f'<line x1="{x-18}" y1="364" x2="{x-18}" y2="434" stroke="{t["hair"]}" stroke-width="2"/>')
    o.append(f'<line x1="{L}" y1="452" x2="{R}" y2="452" stroke="{t["hair"]}" stroke-width="2"/>')
    o.append(T(L, 492, "BRANCH", "mono", 22, "muted", ls=2))
    o.append(T(L, 530, "main", "monob", 30, "ink"))
    o.append(T(cols[1], 492, "COMMIT · FULL SHA, READ BACK AFTER PUSH", "mono", 22, "muted", ls=1))
    o.append(T(cols[1], 528, "3f9c2e14b7a0d58e6c21f09a4b3d7e8c5a61f2b9", "monob", 23, "ink"))
    o.append(f'<line x1="{cols[1]-18}" y1="470" x2="{cols[1]-18}" y2="540" stroke="{t["hair"]}" stroke-width="2"/>')

    # ---- stub
    S = P + 30
    o.append(T(S, 86, "GATE", "mono", 22, "muted", ls=3))
    o.append(T(S, 128, "--confirm-target", "monob", 24, "ink"))
    o.append(T(S, 186, "DESTINATION", "mono", 22, "muted", ls=3))
    o.append(T(S, 228, "owner/repo", "monob", 32, "ink"))
    o.append(T(S, 276, "NOTHING IS PUSHED", "mono", 22, "muted", ls=1))
    o.append(T(S, 304, "BEFORE YOU CONFIRM", "mono", 22, "muted", ls=1))

    # barcode (decorative)
    rnd = random.Random(7)
    x, bars = S, []
    while x < 1228:
        w = rnd.choice([2, 2, 3, 4, 6])
        if x + w > 1228:
            break
        bars.append(f"M{x} 470v72h{w}v-72z")
        x += w + rnd.choice([3, 3, 4, 6])
    o.append(f'<path d="{"".join(bars)}" fill="{t["bar"]}" opacity="{0.9 if mode=="light" else 0.75}"/>')

    # stamp, rotated, crossing the perforation
    cx, cy = 1088, 392
    # outer group carries the CSS animation; inner group keeps the rotate attribute
    stamp = ['<g class="mv-stamp">', f'<g transform="rotate(-9 {cx} {cy})" opacity="{0.92 if mode=="light" else 1}">']
    if mode == "dark":
        stamp.append(f'<rect x="{cx-150}" y="{cy-60}" width="300" height="120" rx="10" fill="none" stroke="{t["acc"]}" stroke-width="14" opacity="0.18"/>')
    stamp.append(f'<rect x="{cx-150}" y="{cy-60}" width="300" height="120" rx="10" fill="{t["paper"]}" fill-opacity="0.55" stroke="{t["acc"]}" stroke-width="5"/>')
    stamp.append(f'<rect x="{cx-140}" y="{cy-50}" width="280" height="100" rx="6" fill="none" stroke="{t["acc"]}" stroke-width="2"/>')
    stamp.append(T(cx, cy - 2, "AWAITING", "head", 50, "acc", "middle", ls=4))
    stamp.append(T(cx, cy + 34, "CONFIRMATION", "headm", 26, "acc", "middle", ls=5.5))
    stamp.append("</g>")
    stamp.append("</g>")
    o += stamp
    o.append("</svg>")
    return "\n".join(o)


# --------------------------------------------------------------------------- WORKFLOW
def workflow(mode):
    t = THEMES[mode]
    W, H = 1280, 600
    o = []
    o.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t d">')
    o.append('<title id="t">Publishing route: inspect, preview, confirm gate, publish, verify, with a resume branch</title>')
    o.append('<desc id="d">A git branch line. On your machine: inspect (accounts, owners, inspect) and preview. A gate marks --confirm-target owner/repo; nothing crosses it without confirmation. On GitHub: publish creates the target branch, verify reads the repository and SHA back. If a publish is interrupted, a branch drops to resume against the same confirmed target and merges back into verify.</desc>')
    o.append(style(t))
    if mode == "light":
        o.append(f'<rect x="24" y="24" width="1232" height="552" transform="translate(8 8)" fill="{t["shadow"]}"/>')
        o.append(f'<rect x="24" y="24" width="1232" height="552" fill="{t["paper"]}" stroke="{t["ink"]}" stroke-width="2"/>')
    else:
        o.append(f'<rect x="24" y="24" width="1232" height="552" fill="{t["paper"]}" stroke="{t["edge"]}" stroke-width="2"/>')
    GX = 640
    o.append(f'<rect x="{GX}" y="25" width="{1255-GX}" height="550" fill="{t["board"]}"/>')
    o.append(T(64, 82, "ON YOUR MACHINE", "head", 30, "ink", ls=2))
    o.append(T(64, 114, "read-only until the gate", "mono", 22, "muted"))
    o.append(T(GX + 44, 82, "ON GITHUB", "head", 30, "ink", ls=2))
    o.append(T(GX + 44, 114, "after you confirm", "mono", 22, "muted"))

    Y = 300
    o.append(f'<line x1="64" y1="{Y}" x2="{GX-40}" y2="{Y}" stroke="{t["ink"]}" stroke-width="5"/>')
    o.append(f'<line x1="{GX+40}" y1="{Y}" x2="1212" y2="{Y}" stroke="{t["ink"]}" stroke-width="5"/>')
    o.append(f'<path d="M1206 {Y-14} L1228 {Y} L1206 {Y+14}" fill="none" stroke="{t["ink"]}" stroke-width="5"/>')
    o.append(f'<line x1="{GX-40}" y1="{Y}" x2="{GX+40}" y2="{Y}" stroke="{t["acc"]}" stroke-width="5" stroke-dasharray="6 6"/>')

    def node(x, name, subs, filled=False):
        bg = t["paper"] if x < GX else t["board"]
        r = [f'<circle cx="{x}" cy="{Y}" r="17" fill="{t["ink"] if filled else bg}" stroke="{t["ink"]}" stroke-width="5"/>']
        r.append(T(x, Y - 100, name, "head", 38, "ink", "middle", ls=1.5))
        for i, s in enumerate(subs):
            r.append(T(x, Y - 66 + i * 28, s, "mono", 22, "muted", "middle"))
        return r

    o += node(170, "INSPECT", ["accounts", "owners · inspect"])
    o += node(420, "PREVIEW", ["branch · full SHA", "owner · visibility"])
    o += node(820, "PUBLISH", ["creates the", "target branch"])
    o += node(1110, "VERIFY", ["reads repo +", "SHA back"], filled=True)

    # gate posts
    o.append(f'<rect x="{GX-34}" y="{Y-150}" width="10" height="250" fill="{t["acc"]}"/>')
    o.append(f'<rect x="{GX+24}" y="{Y-150}" width="10" height="250" fill="{t["acc"]}"/>')
    o.append(f'<rect x="{GX-34}" y="{Y-150}" width="68" height="10" fill="{t["acc"]}"/>')
    o.append(T(GX, Y + 150, "CONFIRM", "head", 38, "acc", "middle", ls=3))
    o.append(T(GX, Y + 184, "--confirm-target", "monob", 22, "acc", "middle"))
    o.append(T(GX, Y + 214, "owner/repo", "monob", 22, "acc", "middle"))

    # resume lane
    by = Y + 150
    rx = 990
    o.append(f'<path d="M820 {Y+17} C820 {by-50} 830 {by} 870 {by} L{rx-24} {by}" fill="none" stroke="{t["ink"]}" stroke-width="4" stroke-dasharray="10 8"/>')
    o.append(f'<path d="M{rx+24} {by} L1060 {by} C1100 {by} 1110 {by-50} 1110 {Y+17}" fill="none" stroke="{t["ink"]}" stroke-width="4"/>')
    o.append(f'<rect x="{rx-17}" y="{by-17}" width="34" height="34" transform="rotate(45 {rx} {by})" fill="{t["board"]}" stroke="{t["ink"]}" stroke-width="4"/>')
    o.append(T(840, Y + 74, "if interrupted", "mono", 22, "muted"))
    o.append(T(rx, by + 60, "RESUME", "head", 32, "ink", "middle", ls=1.5))
    o.append(T(rx, by + 90, "same confirmed target", "mono", 22, "muted", "middle"))
    o.append("</svg>")
    return "\n".join(o)


for mode in ("light", "dark"):
    (OUT / f"hero-{mode}.svg").write_text(hero(mode), encoding="utf-8")
    (OUT / f"workflow-{mode}.svg").write_text(workflow(mode), encoding="utf-8")
print("built", OUT)
