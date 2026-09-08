# Provenance — `youtube-thumbnail-design`

`SKILL.md` in this directory is a **verbatim vendored copy**. Do not edit it. Course-specific
adaptations live in `../../course_thumbnail_spec.md`, which is loaded alongside it; keeping the two
apart is what makes re-installing upstream a one-line operation instead of a merge.

| | |
|---|---|
| Upstream | <https://github.com/qu-skills/skills> (a mirror of `inference-sh/skills`; homepage <https://inference.sh>) |
| Path in repo | `guides/design/youtube-thumbnail-design/SKILL.md` |
| Commit | `becc25649700d5457772a00e5143e28ccf9e5afa` — "docs: update CLI references from `belt app/skill store` to `belt app/skill list`", Mon 3 Aug 2026 |
| Vendored | 1 Sep 2026, 253 lines |
| `sha256` of these bytes | `fc6a642c91e3580718d18532a7330dd4dec97122251cb6ea61c049512564a659` |
| Lockfile `computedHash` | `281aff200fd5b4f0cea0afa3b3547097173f45730774309287e605c2370b4d21` (see `skills-lock.json` at the repo root — a different digest because it is computed over the skill's normalised body, not the raw file) |

## Re-install / refresh

```bash
cd vibely-lesson-agent
npx skills add https://github.com/qu-skills/skills --skill youtube-thumbnail-design
cp .agents/skills/youtube-thumbnail-design/SKILL.md \
   lesson_agent/prompts/skills/youtube-thumbnail-design/SKILL.md
uv run python lesson_agent/thumbnail_agent.test.py   # the drift + section gates below
```

The installed copy at `.agents/skills/youtube-thumbnail-design/SKILL.md` was **byte-identical** to the
upstream clone, so either source vendors the same bytes.

## Licensing

The upstream README carries an **MIT badge** (`opensource.org/licenses/MIT`), but the repository contains
**no `LICENSE` file** — `find . -iname '*licen[cs]e*'` returns nothing at commit `becc2564`. Recorded as
found rather than asserted: no license text has been fabricated here. This is a 253-line design document
vendored for internal use with attribution, which is the reason this file exists.

## Two gates protect this copy, and they are in `thumbnail_agent.test.py`

Both exist because a vendored doc that silently changes shape is the drift the split is meant to kill.

1. **Drift** — these bytes must equal `.agents/skills/youtube-thumbnail-design/SKILL.md` when that path
   is present. It is absent inside the worker image, where the case skips with a loud banner rather than
   passing quietly (rule 21).
2. **Sections** — `thumbnail_agent.load_skill()` whitelists sections by heading and **raises** if any
   expected heading is missing. If upstream renames "Color Strategy", the brief must fail loudly, not
   ship without the colour rules (rule 26).

## What is deliberately not used

The skill generates thumbnails by **diffusion**, through the `belt` CLI (`falai/flux-dev-lora`,
`bytedance/seedream-4-5`). That half is unusable here for a measured reason, not a preference: a course
cover must spell its own title, diffusion cannot spell reliably, and the only text-to-image model
available on Bedrock `us-east-1` is `amazon.nova-canvas-v1:0` (flagged LEGACY). So the model authors SVG
and Chrome rasterises it, and `load_skill()` strips every `belt` invocation and fenced block before the
text reaches the prompt.

Dropped sections: `Quick Start`, `Face Expression Psychology` (a photographed face cannot live in an SVG
cover), `Thumbnail Patterns by Content Type`, `A/B Testing`, `Related Skills`.

Two rules are **inverted** for courses rather than dropped — see `TH-TITLE` in
`course_thumbnail_spec.md`. The skill says a thumbnail should not duplicate the video title, because on
YouTube the title sits next to it. A course card carries no such guarantee, and the title *is* the
payload.
