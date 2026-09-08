# Provenance — `cover-image`

Every file in this directory except this one is a **verbatim vendored copy**. Do not edit them.
Course-specific adaptations live in `../../course_thumbnail_spec.md`, which is loaded alongside;
keeping the two apart is what makes re-installing upstream a one-line operation instead of a merge.
Same convention as `../youtube-thumbnail-design/PROVENANCE.md`.

| | |
|---|---|
| Upstream | <https://github.com/zlh-428/naruto-skills> |
| Path in repo | `skills/cover-image` |
| Repo HEAD when vendored | commit `2cacd40c9a1e0f886c915d4447831fbbe68e58dd` — "refactor: remove desktop-screenshot-peekaboo skill", 29 Jan 2026 |
| Vendored | 4 Sep 2026, 22 files, 24,808 bytes |
| `sha256` of the tree | `33ef6cb507f51b15ae75d61e42d04d9e2d899671781ab1a4b598b67a1d0f12c0` (`find . -type f \| sort \| xargs shasum -a 256 \| shasum -a 256`, with this file absent) |

**`.skillfish.json`'s `sha` is a tree hash, not a commit — checked, because reporting it as a commit
would be a citation nobody could resolve.** The installer wrote
`sha: 1e9765c5db9d0c1efc8c531fc181065d0a64bcc2`, and
`GET /git/trees/2cacd40c…:skills` lists exactly `tree 1e9765c5db9d cover-image`. So it pins the
*directory contents*, which is actually the stronger thing to pin for a vendored subtree: it changes
only when this skill changes, where a commit sha moves whenever anything in the repo does. The file
itself is dropped from the vendored copy (it records the install target, not the skill).

## Re-install / refresh

```bash
cd vibely-lesson-agent
npx skillfish add zlh-428/naruto-skills cover-image -y --project
cp -R .claude/skills/cover-image lesson_agent/prompts/skills/cover-image
rm -f lesson_agent/prompts/skills/cover-image/.skillfish.json
/usr/local/bin/python3 lesson_agent/thumbnail_agent.test.py
```

`skillfish add` needs **`-y --project`**, and without them it hangs rather than failing: with no
`-y` it waits on a confirmation prompt, and with no `.claude/` or `.agents/` directory already
present it prints `No agents detected in this project` and installs **nothing** while exiting 0. It
also writes to *every* detected agent — here both `.claude/skills/` and `.agents/skills/` — and the
two trees were verified byte-identical with `diff -r`, so either path vendors the same bytes.

## Licensing

**Apache License 2.0** — `LICENSE` is present at the repository root (11,357 bytes), unlike
`youtube-thumbnail-design`'s upstream, which carries an MIT badge and no license file. Recorded as
found rather than asserted.

## Why this skill was added

The covers produced under `youtube-thumbnail-design` alone were rejected as *"not so useful and
impressive and informative"*, and two measured gaps explain it. Both are things this skill has and
the existing one does not.

1. **One hardcoded visual style.** `_ART_RULES` rule 5 asks for "rich painterly digital
   illustration" and nothing else, so every cover of every course in every subject is the same oil
   painting. This skill carries a **20-style gallery** — one paragraph each, with named hexes — plus
   a content-signal → style table. `blueprint`, `sketch-notes`, `chalkboard` and
   `editorial-infographic` are registers a course cover should plainly be able to reach and today
   cannot.
2. **No information structure.** A course cover is currently one object, lit. The sibling
   `../infographic/` skill is the one that supplies structure (20 layouts); see its `PROVENANCE.md`.

## What is deliberately not used

- **The whole interactive workflow.** Steps 1–7 are written for a human at a slash command:
  `AskUserQuestion` for style and aspect, a `{topic-slug}/` output directory, timestamped conflict
  resolution, a `source-*.md` copy, a language-preference question. This pipeline has no user at
  generation time — it runs inside an ECS task — so style selection must be automatic and the output
  path is decided by the caller.
- **`references/base-prompt.md`.** It targets a **WeChat article cover at 2.35:1** and mandates
  hand-drawn everything including the text: *"ALL text MUST be hand-drawn style … DO NOT use
  realistic or computer-generated fonts"*. Three conflicts, each measured elsewhere in this project:
  the cover is **16:9** (`TARGET_ASPECT`, and `flux.2-pro` accepts only coarse aspect tiers, not
  pixel sizes); a hand-lettered headline is what `TH-TITLE`'s transcription gate has the hardest
  time reading back; and the file ends by instructing the agent to *"use nano banana pro"*, a model
  choice `OPENROUTER_IMAGE_MODEL` already owns.
- **`--no-title`.** For a course card the title *is* the payload — see `TH-TITLE`, where the same
  inversion is already recorded against the YouTube skill.
- **The 8-character title limit.** Written for Chinese; `MAX_TEXT_WORDS = 6` English words is this
  project's own measured bound.

The **style gallery and the style-selection table are the usable half**, and they are usable almost
verbatim.

## Token budget — why the gallery cannot simply be pasted in

24,808 bytes is roughly 6.2k tokens for `cover-image` alone, and the sibling `infographic` skill is
another 62 KB. The `<Game>` registry already solved this exact problem in this repo and the answer
is the same: the **one-line-per-entry gallery table** goes in the cached system half, and the
**detailed `references/styles/<style>.md`** (roughly 200 tokens) is injected only for the style
actually chosen. Loading every style file would cost ~35k tokens per cover to use one of them.
