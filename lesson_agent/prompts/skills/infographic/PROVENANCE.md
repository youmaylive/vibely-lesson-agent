# Provenance — `infographic`

Every file in this directory except this one is a **verbatim vendored copy**. Do not edit them.
Same convention as `../youtube-thumbnail-design/PROVENANCE.md` and `../cover-image/PROVENANCE.md`.

| | |
|---|---|
| Upstream | <https://github.com/zlh-428/naruto-skills> |
| Path in repo | `skills/infographic` |
| Repo HEAD when vendored | commit `2cacd40c9a1e0f886c915d4447831fbbe68e58dd` — "refactor: remove desktop-screenshot-peekaboo skill", 29 Jan 2026 |
| Subtree hash recorded by the installer | `8ea69ff04b0ee589f1e128db1faf18df51f39dd3` — a **tree** sha, resolved against `GET /git/trees/2cacd40c…:skills`, not a commit (see `../cover-image/PROVENANCE.md` for the check) |
| Vendored | 4 Sep 2026, 41 files, 61,970 bytes |
| `sha256` of the tree | `99a168cd43a0e01488f7cd1ce0edca8a57bd03c249a557f5a27d88630d86bd17` |
| License | **Apache 2.0**, `LICENSE` present at the repo root |

Re-install is the same three lines as `cover-image`, with `infographic` in place of the skill name,
including the **`-y --project`** requirement and the silent no-op when no agent directory exists.

## Why this one is here, and it is not a duplicate of `cover-image`

It was not asked for by name — *"you can find other similar skills"* was. It earns its place because
it is the only one of the seven skills in that repo that supplies the dimension the complaint is
actually about. The word in the complaint was **informative**, and a cover is informative when it has
*structure*, not when it has a nicer style:

| skill | supplies | this project has |
|---|---|---|
| `youtube-thumbnail-design` (already vendored) | attention: contrast, faces, colour strategy | yes — the whole current design |
| `cover-image` | **20 visual styles** + a content→style table | **no** — one hardcoded painterly register |
| `infographic` | **20 layouts × 17 styles**, layout = information structure | **no** — one object, lit |

Its `Layout Gallery` is the useful artifact, and several rows map onto a course spine almost
mechanically: `linear-progression` for a course that is a sequence of modules, `hierarchical-layers`
for one that builds up, `hub-spoke` for one central concept with satellites, `tree-branching` for a
taxonomy, `winding-roadmap` for a journey, `structural-breakdown` for an anatomy. That is a
**property of the curriculum we already parse** — `render_curriculum` prints `builds:` and
`teaches:` lines for every module — so the layout can be chosen from the spine rather than guessed.

`references/analysis-framework.md` and `references/structured-content-template.md` are also worth
reading before writing any of this: they are the closest thing in either skill to a specification of
*what to say* on an educational graphic, as opposed to how to make it pretty.

## The thing to resolve before any of this can be used

**An infographic layout puts labelled text on the picture, and `TH-TITLE` currently forbids all text
except the headline.** The gate compares a vision transcription of the *whole image* against the
headline by string equality, and the clause `build_prompt` appends says in as many words: *"anywhere
the object would carry writing, paint it too small and blurred to read as words."* So every layout in
this gallery is unreachable today — not by preference, by gate. That is the same shape as the
`TH-MARKS` / `TH-TITLE` collision already recorded in `course_thumbnail_spec.md`, one level up: a
rule that protects the title also forbids the cover from saying anything. Resolving it needs the
label text to be *declared and checked before the image is bought*, the way `SOURCE:` and `MARKS:`
already are, so that the transcription can be compared against headline-plus-declared-labels and
stay exact. Nothing here should be wired in until that is designed.

## What is deliberately not used

- The interactive workflow (`AskUserQuestion` for layout × style, `{topic-slug}/` directories,
  language questions) — no user exists at generation time.
- `references/base-prompt.md`, for the same reasons as `cover-image`'s: it targets a non-16:9 WeChat
  format and names its own image model.
- Portrait and square aspects. The cover is 16:9 (`TARGET_ASPECT`), and `flux.2-pro` accepts coarse
  aspect tiers only.
- The 17 styles here overlap `cover-image`'s 20 without being identical (`craft-handmade`,
  `claymation`, `lego-brick`, `subway-map`, `ikea-manual`, `knolling` are unique to this one;
  `chalkboard` and `pixel-art` appear in both). **Two galleries must not become two sources of
  truth** — whichever is used, one list gets picked and the other is cited as unused, or this is
  rule 23's divergence with prettier names. And the overlap is not even consistent, which is the
  concrete form of that risk: measured with `diff`, `chalkboard.md` is **byte-identical** across the
  two skills while `pixel-art.md` **differs**. So "they share some styles" is false in detail — two
  files with the same name and different contents is exactly the divergence to refuse up front.
