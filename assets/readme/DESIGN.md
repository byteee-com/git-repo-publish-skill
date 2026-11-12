# README design record

Produced with the `readme-stylist` skill (concept-first workflow). Keep new README assets consistent with this record.

## Concept

**A first publish is a boarding pass.** Your project travels from a local path to `owner/repo`; it is checked at a gate and only boards after you confirm.

Signature details:

- **Torn stub** with a perforation: the part that is held back until you confirm
- **"Awaiting confirmation" stamp** crossing the stub: the `--confirm-target` gate
- **Route line** `LOCAL ─○─○─‖ ‖- - -> GITHUB`: solid commits up to the gate, dashed after it (not yet travelled)

Rejected candidates:

| Candidate | Why rejected |
| :-- | :-- |
| Shipping manifest / customs form | Same evidence fit, but harder to recognise in 3 seconds at README width |
| Terminal session showing `inspect` output | The skill is driven through chat, not a single command, so a terminal would misrepresent how it's used |

## Evidence

The hero is a re-typeset version of the skill's real publish preview. Field names and order come from `SKILL.md` ("准备并预览": platform, path, branch and full SHA, account, owner, repository, visibility, protocol). Values are obvious placeholders: `~/Code/project`, `@you`, `owner/repo`, and an example 40-character SHA. They are not a real repository.

The workflow nodes use real subcommands and stages: `accounts`, `owners`, `inspect`, preview, `--confirm-target`, publish, read-back verify, `resume` (from `SKILL.md` and `references/github.md`).

## Tension

- Extreme scale: 160px `LOCAL` / `GITHUB` against 22px field labels (≈ 7:1)
- A single accent, used only on the gate and the stamp
- The stamp is rotated −9° and is the only off-grid element

## Tokens

| Token | Light: paper ticket | Dark: night departure board |
| :-- | :-- | :-- |
| Paper | `#F2ECDF` | `#0F1828` |
| Ink | `#1B1A17` | `#F1EADB` |
| Muted | `#6B6457` | `#8D9AB0` |
| Hairlines | `#CFC6B4` | `#24324B` |
| Accent | `#D4430F` (red rubber stamp) | `#FFB23F` (amber signal, with glow ring) |
| GitHub-side zone | `#E7DFCE` | `#16223A` |

Dark is a separate scene, not an inversion. It adds a dot-matrix texture on the stub, split-flap seams through the big letters, and a glowing stamp. Light uses a hard offset shadow, like a printed card.

## Type

All text is converted to paths, so it renders identically everywhere. Fonts are SIL OFL:

- Display: Bebas Neue (`LOCAL`, `GITHUB`)
- Headings and stamp: Oswald Bold / Medium
- Fields and code: JetBrains Mono Regular / Bold
- Minimum size: 22px on a 1280 canvas, ≈ 14px at GitHub's ~830px column

## Files

| File | Canvas | Use |
| :-- | :-- | :-- |
| `hero-light.svg` / `hero-dark.svg` | 1280 × 600 | README top, switched with `<picture>` |
| `workflow-light.svg` / `workflow-dark.svg` | 1280 × 600 | "How it works" |
| `hero-zh-CN-{light,dark}.svg` / `workflow-zh-CN-{light,dark}.svg` | 1280 × 600 | Simplified Chinese README |
| `src/*.svg` | | Editable sources with live `<text>` |
| `src/build.py` | | Generator. `FONTS_DIR=<dir with the fonts> python3 build.py <out>`, then run readme-stylist `text_to_path.py` with a font map (`disp`, `head`, `headm`, `mono`, `monob`) |
| `src/localize_zh.py` | | Reuses the outlined English assets and renders translated labels with Noto Sans SC |

Generate the Chinese artwork with `python3 assets/readme/src/localize_zh.py <font-directory>` from the project root. The script uses FontTools and [Noto Sans SC Regular and Bold](https://github.com/notofonts/noto-cjk/tree/main/Sans/SubsetOTF/SC) under the SIL Open Font License.

## Review log

Rendered with `rsvg-convert` at 1280 / 830 / 360px and checked against `readme-stylist/references/self-check.md`.

| Round | Problem | Change |
| :-- | :-- | :-- |
| 1 | Workflow: step captions sat under the line and collided with the gate label and the resume branch | Moved names and captions above the line; the gate label and resume lane now own the space below |
| 1 | Hero: gate posts were too thin to read as a gate at 830px | Thicker, taller posts; slightly smaller display type for more route length |
| 1 | Dark hero: split-flap seam barely visible | Seam thickened from 3 to 5px |
| 2 | Workflow: PUBLISH crowded the gate post; VERIFY too close to the arrow | Moved PUBLISH right and VERIFY left; recentred the resume lane |
| 3 | "interrupted" label collided with the resume diamond | Moved it next to the drop-down branch: "if interrupted" |

## Facts shown in assets

The README links to the project license. The illustrations show the publishing workflow.
