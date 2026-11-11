# README design record

Produced with the `readme-stylist` skill. Keep new README assets consistent with this record.

## Direction

- **Skeleton:** document (spec-sheet layout, native Markdown first)
- **Style:** swiss-grid — left-aligned, no rounded corners, gradients, or shadows; one accent color
- **Weight:** L2 — hero plus one workflow diagram; everything else is Markdown
- **Why:** the skill is used through conversation, not a command worth showing in a terminal hero. Its value is a verifiable process (preview → explicit confirm → verify / resume), which reads best as a grid and a flow.

## Tokens

| Token | Light | Dark |
| :-- | :-- | :-- |
| Background | `#FFFFFF` | `#0D1117` |
| Foreground / rules | `#111111` | `#F0F3F6` |
| Muted text | `#5C5C5C` | `#9198A1` |
| Accent | `#1F6FEB` | `#4493F8` (hero mark) / `#1F6FEB` fill with white text (diagram) |

The accent is GitHub blue, used only twice: the square mark in the hero and the **Confirm** step in the diagram — the step that defines this skill.

## Type

- Display and labels: `"Helvetica Neue", Helvetica, -apple-system, "Segoe UI", "Noto Sans", Arial, sans-serif`
- Mono: `ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace`
- Hero title 96px (letter-spacing −4px), subtitle 30px, labels 15–16px uppercase with +1.6px tracking
- Text currently uses system font stacks; run `text_to_path.py` from readme-stylist if exact rendering across platforms is needed

## Files

| File | Canvas | Use |
| :-- | :-- | :-- |
| `hero-light.svg` / `hero-dark.svg` | 1280 × 480 | README top, switched with `<picture>` |
| `workflow-light.svg` / `workflow-dark.svg` | 1280 × 400 | "How it works" section |

## Facts shown in assets

All values come from `SKILL.md`, `README.md`, and `references/github.md`: client list, Git / gh / Python 3.8+, macOS / Linux, and the inspect → preview → confirm → publish → verify / resume flow. No license, star, or usage figures are shown — the repository has no LICENSE file yet.
