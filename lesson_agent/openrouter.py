"""OpenRouter: one image-generation call and one vision transcription call.

Two functions, one HTTP client, one key. Used only by `thumbnail_agent.py` — the
in-lesson diagram path stays on Bedrock through `svg_agent.py` and does not import
this.

Why OpenRouter rather than Bedrock
----------------------------------
Bedrock's us-east-1 catalogue has exactly one text-to-image model (`nova-canvas-v1:0`,
flagged LEGACY) and its Stability models are edit/upscale/inpaint only. It also returns
**no cost field** for image models, which is AGENTS.md rule 28: any path calling Bedrock
directly must price tokens itself or book $0.00. OpenRouter returns `usage.cost` inline,
in USD, measured — so the number booked here is the real one rather than an estimate at a
rate that goes stale.

Two things about this endpoint that shape the code below, both measured against the live
API rather than read in the docs:

* **`media_type` is not negotiable.** `output_format: "png"` is accepted by only a few
  models; the rest return whatever they return. Measured on 5 models with an identical
  request: 4 returned `image/png` and `bytedance-seed/seedream-4.5` returned
  `image/jpeg`. Pillow is not in this venv, so there is nothing to convert with — and
  the cover ships to an S3 key ending `.png` served as `image/png`. So the caller must
  treat a non-PNG as a hard failure, and `generate_image` returns the media type rather
  than swallowing it.
* **There is no `negative_prompt`.** Every "do not draw X" has to live inside the prompt
  text, which is why the art direction in `thumbnail_agent.build_prompt` states its
  exclusions in prose.

A response that carries no image is a NAMED failure, never a fall-through. The
content-policy refusal shape is undocumented, so anything that is not
`data[0].b64_json` raises with the body attached: the alternative is a caller that reads
"no image" as "empty image" and writes a zero-byte cover.
"""

from __future__ import annotations

import base64
import json
import os
import re

import httpx

import usage

API_BASE = os.environ.get("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")

# The step-0 bake-off winner. Five models, one identical prompt, all five spelled the
# headline correctly (which is the finding that made this whole pivot possible — the
# premise the SVG generator was built on, "diffusion cannot spell", is no longer true).
# They separated on everything else:
#
#   model                            $/img   secs  media_type   dims        MB
#   black-forest-labs/flux.2-pro     0.045    19   image/png    1824x1024  2.96
#   bytedance-seed/seedream-4.5      0.040    13   image/JPEG   —          0.89
#   google/gemini-3-pro-image        0.135    33   image/png    2752x1536  4.59
#   openai/gpt-image-2               0.131    91   image/png    1536x864   1.61
#   sourceful/riverflow-v2.5-pro     0.260   110   image/png    2560x1440  5.56
#
# flux.2-pro is 3x cheaper and 5x faster than the next model that returns PNG, and it
# was the only one of the five whose composition had no hard vertical seam where the
# reserved text column met the art (seedream and gemini both drew the panel edge as a
# visible line). seedream is disqualified structurally, not aesthetically: JPEG.
#
# **SUPERSEDED 8 Sep 2026 — that table is a price per CALL, and the thing being bought is a
# COVER.** The numbers above are all correct and the conclusion drawn from them was wrong,
# because a cover costs one image *plus every image the gates reject*. Re-measured over 5
# topics x 3 models, one run, same art direction in all three columns so the image model is
# the only variable (`covers-review/three_models.py`, 15/15 shipped, $3.2827):
#
#   model                        att/cover   $/cover   s/cover   hard fails   advisories
#   openai/gpt-5.4-image-2            1.2     0.117        70         0            4
#   google/gemini-3-pro-image         1.4     0.244        76         0            7
#   black-forest-labs/flux.2-pro      2.6     0.295       119         1            7
#
# So the incumbent was the **most expensive of the three**, at 2.5x, on a table that says it
# is 3x the cheapest. It needs 2.6 attempts where gpt needs 1.2, and retries dominate: the
# image price is under a third of a cover. Its one hard failure cost $0.5646 for a cover that
# shipped with no headline and two blank label plates.
#
# gpt-5.4-image-2 also painted the **only legible labelled cover** this project has produced
# (`structural-breakdown`, three curriculum terms on brass nameplates, attempt 1, zero
# advisories) after that path had failed twice on flux — so the labelled layout's blocker was
# the image model, not the prompt.
#
# Two things this does NOT claim. Five covers per model is a small sample, and the models were
# not compared on taste — only on what the gates and the clock measured. And
# `google/gemini-3.1-flash-image` is untested at 5 topics while measuring $0.110/cover at
# attempt 1 on 2 (1 Sep), i.e. it may yet be cheaper; it was left out of the sweep only to
# avoid spending 5 of 15 covers on a second Google entry.
#
# Env-overridable so retuning needs no image rebuild — the SVG_FLOOR / GAME_FLOOR_RATE
# precedent. That is also the migration path: this default is what an unconfigured caller
# gets, and `settings.OPENROUTER_IMAGE_MODEL` must agree with it (asserted by
# `memebu-engine-v2/src/engine/config/worker_env.test.py`).
DEFAULT_IMAGE_MODEL = os.environ.get(
    "OPENROUTER_IMAGE_MODEL", "openai/gpt-5.4-image-2"
)

# The vision model that reads the cover back. Accuracy is worth more than the saving
# here: a transcription that is wrong about a correctly-spelled headline costs a whole
# image generation ($0.045), which buys about 11 of these.
DEFAULT_VISION_MODEL = os.environ.get(
    "OPENROUTER_VISION_MODEL", "anthropic/claude-sonnet-5"
)

# The text model that writes the art direction. It used to be Bedrock, through
# `svg_agent._llm_call_async`, and moving it here is not tidying — it is the difference
# between a cover phase that runs in production and one that cannot.
#
# `workers/Dockerfile` launches the worker as
# `uv run --directory /app/ontology-engine python /app/workers/entrypoint.py`, and
# `phases/thumbnail.py` imports `thumbnail_agent` **in-process**. So the import runs under
# *ontology-engine's* venv, which has `httpx` but NOT `anthropic` — measured in the built
# arm64 image, where `from svg_agent import _llm_call_async` failed with
# `No module named 'anthropic'` and the phase reported `##PHASE:thumbnail:failed##` on
# every course. Declaring `anthropic` in ontology-engine's pyproject would make one
# project's venv responsible for another's dependencies (rule 23's shape); running the
# agent as a subprocess would add a process boundary and a second usage path. Talking to
# one provider over `httpx` removes the dependency instead of relocating it.
#
# It also removes the `MODEL` trap at the source: there is no longer a Bedrock model name
# anywhere in this path, so nothing can 400 on being handed the wrong kind of name.
DEFAULT_TEXT_MODEL = os.environ.get(
    "OPENROUTER_TEXT_MODEL", "anthropic/claude-sonnet-5"
)

# Measured: flux 19s, gemini 33s, gpt-image-2 91s, riverflow 110s. 300s leaves room for
# the slow end plus a queue, and is well inside the ECS phase's own budget.
IMAGE_TIMEOUT = float(os.environ.get("OPENROUTER_IMAGE_TIMEOUT", "300"))
VISION_TIMEOUT = float(os.environ.get("OPENROUTER_VISION_TIMEOUT", "120"))

# Whether the art-direction turn may think before answering. **Off**, and the reason is a
# measurement rather than a preference — see `complete_text`. `1`/`true`/`on` turns it back on
# without a rebuild, because the honest description of that setting is "the configuration that
# truncated three times", not "unsupported".
ART_THINKING = os.environ.get("OPENROUTER_ART_THINKING", "0").strip().lower() in (
    "1", "true", "yes", "on",
)


class OpenRouterError(RuntimeError):
    """A call that did not return what it was asked for.

    One exception type with a spoken reason, rather than a family: every caller here
    does the same thing with it (record the reason, retry or ship text-free), so the
    distinction would be for nobody.
    """


def _key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        # Named, because this is the failure that would otherwise be silent on exactly
        # one launch path: the cover phase is advisory, so a missing key on the
        # regenerate route (but not the curriculum route) would degrade to "no cover"
        # with nothing to read. See the three env-construction sites in
        # `memebu-engine-v2`.
        raise OpenRouterError(
            "OPENROUTER_API_KEY is not set — no cover can be generated. It must be "
            "present in the worker's environment; see routes/courses.py (both launch "
            "sites) and services/pipeline.py::_build_container_env"
        )
    return key


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_key()}",
        "Content-Type": "application/json",
    }


def _book(payload: dict, *, calls: int = 1) -> float:
    """Fold one response's `usage` into the process-wide accumulator.

    `usage.record` is the generic entry point — it takes a cost with zero tokens, which
    is exactly the shape an image call has. Returns the cost so the caller can report
    the per-call figure as well as the running total.

    Note `prompt_tokens`/`completion_tokens` ARE booked: for an image call the
    completion tokens are image tokens (measured: 7,291 for one flux cover), which are
    not text tokens but are the only token figure the API reports, and a run that books
    zero tokens against a real cost is the asymmetry AGENTS.md rule 27 was written
    about.
    """
    u = payload.get("usage") or {}
    cost = float(u.get("cost") or 0.0)
    usage.record(
        cost_usd=cost,
        input_tokens_delta=int(u.get("prompt_tokens") or 0),
        output_tokens_delta=int(u.get("completion_tokens") or 0),
        calls=calls,
    )
    return cost


async def _post(path: str, body: dict, timeout: float) -> dict:
    """POST JSON, return the decoded body, raise `OpenRouterError` on anything else."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(
                f"{API_BASE}{path}", headers=_headers(), json=body
            )
        except httpx.HTTPError as exc:
            raise OpenRouterError(f"{path}: {type(exc).__name__}: {exc}") from exc

    if resp.status_code >= 400:
        # The body carries the actual reason (bad model id, moderation, credit) and is
        # the only useful thing here; the status alone sends someone reading the wrong
        # code. Truncated because a 4xx body can carry the whole echoed prompt.
        raise OpenRouterError(
            f"{path}: HTTP {resp.status_code}: {resp.text[:600]}"
        )
    try:
        return resp.json()
    except json.JSONDecodeError as exc:
        raise OpenRouterError(
            f"{path}: HTTP {resp.status_code} but the body is not JSON: "
            f"{resp.text[:300]!r}"
        ) from exc


def parse_image_response(payload: dict) -> tuple[bytes, str]:
    """`(png_bytes, media_type)` out of an `/images` response body.

    Split out from the HTTP call so the parse can be tested against recorded bodies with
    no key and no network — including the ones that carry no image, which are the whole
    reason this is a function.
    """
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise OpenRouterError(
            "the response carried no image: `data` is empty or absent. This is also "
            f"where a content-policy refusal arrives (shape undocumented): {json.dumps(payload)[:500]}"
        )
    item = data[0]
    if not isinstance(item, dict):
        raise OpenRouterError(f"data[0] is not an object: {json.dumps(item)[:300]}")

    b64 = item.get("b64_json")
    if not b64:
        raise OpenRouterError(
            f"data[0] has no `b64_json`: keys were {sorted(item)!r}. A URL-returning "
            "variant would land here — it must be fetched, not assumed absent"
        )
    try:
        raw = base64.b64decode(b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise OpenRouterError(f"`b64_json` is not valid base64: {exc}") from exc
    if not raw:
        raise OpenRouterError("`b64_json` decoded to zero bytes")

    # Reported media type AND the magic bytes, because they can disagree and the one
    # that decides whether a browser renders the cover is the bytes. Measured:
    # seedream's `image/jpeg` really was `ffd8ffe0`, so on that model they agreed — but
    # trusting the label alone is how a mislabelled body would reach an S3 key that
    # promises PNG.
    media_type = str(item.get("media_type") or "").strip().lower()
    sniffed = "image/png" if raw[:8] == b"\x89PNG\r\n\x1a\n" else ""
    if media_type == "image/png" and not sniffed:
        raise OpenRouterError(
            f"the response says image/png but the bytes do not start with the PNG "
            f"signature (first 8: {raw[:8].hex()})"
        )
    return raw, (media_type or sniffed or "application/octet-stream")


async def generate_image(
    prompt: str,
    *,
    model: str = "",
    aspect_ratio: str = "16:9",
    output_format: str = "png",
    extra: dict | None = None,
) -> tuple[bytes, str, float]:
    """Generate one image. Returns `(bytes, media_type, cost_usd)`.

    Does NOT enforce PNG — it reports the media type and lets the caller fail closed.
    That split is deliberate: this module's job is to say truthfully what came back, and
    "a JPEG is unusable" is a fact about the S3 key template, which lives upstream.

    `aspect_ratio`, not a pixel size: **no model on this endpoint accepts an explicit
    `size`**. Only a ratio plus, on some models, a coarse `resolution` tier — which is
    why the caller checks a dimension FLOOR rather than an exact figure.
    """
    body: dict = {
        "model": model or DEFAULT_IMAGE_MODEL,
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "n": 1,
    }
    if output_format:
        body["output_format"] = output_format
    if extra:
        body.update(extra)

    payload = await _post("/images", body, IMAGE_TIMEOUT)
    cost = _book(payload)
    raw, media_type = parse_image_response(payload)
    return raw, media_type, cost


# What the vision model is asked, in TWO groups — and the split is not a refinement, it is
# the fix for a measured defect that cost two of five covers their entire headline.
#
# This prompt used to ask for "every word of text visible in this image … including
# watermarks", one flat list, and `account_transcription` then required every word in it to
# be the headline or a declared label. That is correct for a caption and wrong for the
# picture's own furniture, and the two halves of this project were enforcing opposite
# contracts: `MARKS:` in the art direction deliberately ASKS for the numerals on a price
# board and the part codes on a casting, because an object with its markings scrubbed off
# reads as blank furniture. `lexical_text` already tolerated pure digits for exactly this
# reason. What it could not tolerate is a stamped code with a letter in it, and the live run
# of 4 Sep 2026 measured what that costs:
#
#   recursion       attempt 1 had the headline correct and was rejected over 'Ø09' 'Ø11'
#                   'Ø38' '1L' — diameter symbols on the chain tags. The correction turn then
#                   told the model to keep incidental writing unreadable, it complied by
#                   losing the headline too, and attempts 2-4 had no title at all. SHIPPED
#                   WITH NO HEADLINE.
#   python-oop      attempt 2 painted the headline AND all three declared labels correctly,
#                   and was rejected over '19068G' 'XHPVE' '501S' — stamped part numbers it
#                   had been asked for. SHIPPED WITH NO HEADLINE.
#   economics       'GRAD' 'GRADO' 'X17' on the crate and price slate; 4 attempts.
#   immune-system   'HR' 'GIOT' 'HI' on a syringe barrel; 4 attempts.
#
# Four of five covers, and the failure mode is the worst one this gate can produce — worse
# than any defect it was written to catch, which is the same finding `lexical_text` already
# records one level down.
#
# So the discrimination moves to where the information actually is: the PIXELS. A string
# heuristic cannot tell 'GRADO' on a chalk slate from 'MASTERCLASS' in 90pt across the
# corner — the transcript does not say how big a glyph was or where it sat. A vision model
# can see both. Asking it to sort the text into "deliberately placed lettering" and "writing
# that belongs to an object in the picture" is one question about the thing itself rather
# than a rule reasoned about its shadow, and it keeps the headline check exactly as strict:
# a watermark, caption, subtitle and signature are all named in the TEXT group on purpose.
#
# The accepted risk, stated rather than discovered later: a vision model that files a real
# watermark under MARKS lets it through. That is the direction to be wrong in — a stray
# watermark is a blemish, and the alternative is measured above at 2 covers in 5 with no
# title on them.
TRANSCRIBE_PROMPT = (
    "Read the text in this image back to me, sorted into two groups.\n\n"
    "TEXT — the deliberately placed lettering: the large headline, and any caption, "
    "subtitle, tagline, watermark, signature, credit line or logo wordmark laid over the "
    "picture. This is text that was added ON TOP of the image.\n"
    "MARKS — the small incidental writing that belongs to an object inside the picture: "
    "numbers or codes stamped, etched, printed, chalked or engraved onto a thing that is "
    "being depicted. Dial figures, gauge scales, part numbers, dimension callouts, price "
    "boards, the label on a bottle, the spine of a book, digits on a keypad.\n\n"
    "Transcribe both groups exactly as spelled, in reading order — do not correct "
    "spelling and do not guess at a word you cannot read clearly. Output exactly two "
    "lines and nothing else, in this order:\n"
    "TEXT: <the words, or NO_TEXT if there is no added lettering>\n"
    "MARKS: <the words, or NONE if no object carries writing>"
)

NO_TEXT = "NO_TEXT"
NO_MARKS_SEEN = "NONE"

_TRANSCRIBE_LINE = re.compile(
    # `[^\n]*` and not `.*`: each group is one line, and `re.DOTALL` is deliberately absent
    # so a MARKS line cannot be swallowed into TEXT's capture.
    r"^[ \t]*(TEXT|MARKS)[ \t]*:[ \t]*([^\n]*)$",
    re.IGNORECASE | re.MULTILINE,
)


def parse_transcription(reply: str) -> tuple[str, str]:
    """Split a `TRANSCRIBE_PROMPT` reply into `(added_text, object_marks)`.

    **Falls back to the whole reply as `added_text`**, which is the strict direction and
    therefore the safe one: a model that ignores the format, or an older cached reply, is
    then judged exactly as it was before this split existed. Degrading toward the check that
    burns attempts is acceptable; degrading toward the one that passes everything is not
    (rule 31 — this is a gate, so an ambiguous input fails closed).

    A reply carrying only `MARKS:` still yields an empty `added_text`, and that is right: it
    is a positive statement that no lettering was added, not a parse failure.
    """
    found = {m.group(1).upper(): m.group(2).strip() for m in _TRANSCRIBE_LINE.finditer(reply)}
    if not found:
        return reply.strip(), ""
    text = found.get("TEXT", "")
    marks = found.get("MARKS", "")
    if text.strip().upper() in ("", NO_TEXT, "NONE", "N/A"):
        text = ""
    if marks.strip().upper() in ("", NO_MARKS_SEEN, NO_TEXT, "N/A"):
        marks = ""
    return text, marks

# The second question, and the reason it exists: `TRANSCRIBE_PROMPT` above asks for words,
# so a vision model reading a headline answers with the WORD IT EXPECTS. A shipped cover
# painted `CLASSÆS` — an æ ligature where `ES` belonged — and transcribed clean as
# `MASTER PYTHON CLASSES`, passing the one gate the whole painted-title design rests on.
# Asking for the glyphs one at a time removes the word from the loop: there is no word for
# the model to fall back on, so a shape that is not a letter has nowhere to hide.
#
# Every clause here is doing work. "even if the result is not a real word" and "do not
# correct it" are the anti-autocomplete instructions; without them the model repairs the
# defect being looked for. Word boundaries are deliberately NOT asked for — the comparison
# in `thumbnail_agent` is on letters and digits alone, since spacing is what `transcribe`
# already checks and a model asked to mark gaps would spell the marker.
#
# "even if it is set on more than one line" is the one clause added from a live failure
# rather than from reasoning. An image model breaks a long headline across two or three
# lines whenever it likes — nothing in the prompt asks it not to, and it should not,
# because a four-word headline on one line is unreadable at card size. But "the largest
# headline text" then names something ambiguous: a model that answers with the largest
# *line* spells a truthful prefix of the headline, and `TH-GLYPH` compares against the
# whole one, so a perfectly-painted cover fails hard on a wording defect in the question.
# `transcribe` cannot substitute here — it already returns line breaks as `\n` and the
# normaliser folds them, so it is blind to exactly this. Whether it caused the observed
# `MARKET` for `MARKET SUPPLY AND DEMAND` is unproven and deliberately not claimed: the
# next cover's headline came back on one line, so nothing tripped the gate either way.
# The clause is cheap, the failure it removes is a hard one, and the direction is safe —
# asking for every line can only ever make the spelled string a *longer* superset.
SPELL_PROMPT = (
    "Look at the largest headline text in this image — the course title. It may be set "
    "on one line or broken across two or more lines; read all of its lines, top to "
    "bottom, as one continuous headline. Spell it out one character at a "
    "time, in order, separating every character with a single space. Copy each shape "
    "exactly as it is drawn, even if the result is not a real word, is misspelled, or "
    "uses an unusual character — do not correct it, do not complete it, do not guess "
    "which word was intended. Do not spell any smaller text, label or watermark. "
    "Output only the spelled-out characters and nothing else. "
    "If the image contains no text at all, output exactly: NO_TEXT"
)


def parse_chat_response(payload: dict) -> str:
    """The assistant's text out of a `/chat/completions` body."""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise OpenRouterError(
            f"the response carried no `choices`: {json.dumps(payload)[:400]}"
        )
    message = (choices[0] or {}).get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        # Some providers return content parts rather than a string.
        content = "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    if not isinstance(content, str) or not content.strip():
        # An empty completion is NOT "the image has no text" — it is a failed read, and
        # conflating them would let a broken vision call silently pass a cover whose
        # headline is misspelled. The caller must see this as an error.
        #
        # Truncation gets its own sentence because it is a different defect with a different
        # fix, and the generic message hid it: measured on a real cover run, the art
        # direction came back `content: null` with `finish_reason: "length"` because the
        # model spent the whole `max_tokens` budget on a `reasoning` block. "returned no
        # text" is true and useless. Note what this disproves: reasoning is NOT off by
        # default for every model here.
        #
        # The two cases name DIFFERENT fixes, so they are two messages (rule 24 — feedback
        # must be fixable by the thing it names). This message said "raise max_tokens" for
        # both, and that advice was followed three times — 2000 → 4000 → 8000 — while the
        # thinking grew to fill each new ceiling. When `reasoning` is present the cap is not
        # the lever; `reasoning: {"enabled": false}` is, and it is the only setting measured
        # to be honoured (`{"max_tokens": 2000}` billed 6233).
        if (choices[0] or {}).get("finish_reason") == "length":
            thought = len(str(message.get("reasoning") or ""))
            raise OpenRouterError(
                "the completion was truncated by max_tokens before any text was emitted "
                f"(finish_reason=length, {thought} chars of `reasoning`). "
                + (
                    "Send reasoning={'enabled': False} for this call — raising max_tokens "
                    "does not help, the thinking grows to fill it"
                    if thought
                    else "Raise max_tokens for this call — no reasoning was produced, so "
                    "the reply itself did not fit"
                )
            )
        raise OpenRouterError(
            f"the vision model returned no text: {json.dumps(choices[0])[:400]}"
        )
    return content.strip()


async def _chat(
    content, *, model: str, max_tokens: int, timeout: float, reasoning: dict | None = None
) -> tuple[str, float]:
    """One `/chat/completions` turn. Returns `(text, cost_usd)`.

    The single transport for every text-out call here — the art direction, the
    transcription and the critique differ only in what `content` carries and which model
    reads it. One function so that booking (`_book`) and the "an empty completion is a
    failed read, not an empty answer" rule cannot end up implemented twice with a
    difference (rule 23).
    """
    body = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        # Bounded so a model that decides to write an essay is truncated rather than
        # expensive.
        "max_tokens": max_tokens,
    }
    # Passed through verbatim, per caller. Only `complete_text` sends it: the vision calls run
    # on 500 and 600 tokens and do not deliberate, and a parameter sent where it changes nothing
    # is a parameter whose effect nobody can measure later.
    if reasoning is not None:
        body["reasoning"] = reasoning
    payload = await _post("/chat/completions", body, timeout)
    cost = _book(payload)
    return parse_chat_response(payload), cost


async def complete_text(
    prompt: str, *, model: str = "", max_tokens: int = 8000
) -> tuple[str, float]:
    """One text-only completion. Returns `(text, cost_usd)`.

    This writes the art direction. `max_tokens` is far above the vision calls' 300 because
    the reply is a headline plus a paragraph of art direction, and a truncated paragraph is
    worse than a slightly expensive one: `parse_art_direction` would either reject it
    (costing a whole retry) or accept a sentence that stops mid-clause and send it to the
    image model.

    **4000, up from 2000, measured rather than chosen.** A real correction turn came back
    with `content: null` and `finish_reason: "length"` — the model had spent the entire
    budget on a `reasoning` block deliberating over which curriculum entry to cite, and the
    cover phase then died with "returned no text". So the cap bounds reasoning as well as
    output, and a prompt that invites deliberation (the TH-GROUND citation) can exhaust it.
    Costs nothing on a turn that does not reason: this is a ceiling, not a reservation.

    That measurement also corrects what this docstring used to claim — that OpenRouter's
    default has thinking off, "so the behaviour matches without asking for it". It does not
    for every model.

    **Then 8000, and 8000 did not work either — the raise was never the fix.** 2000 → 4000 →
    8000, and at every cap the turn came back `content: null` with `finish_reason=length`: 3929
    and 3486 characters of `reasoning` at 4000, and **7897 at 8000** (`python-oop`, 4 Sep 2026),
    each one costing an attempt out of `MAX_ATTEMPTS = 4`. Thinking grew to fill whatever it was
    given, so raising a shared ceiling is a race the model wins every time.

    **A `reasoning.max_tokens` partition was tried next and is silently IGNORED — measured, and
    that is why this is a flag and not a budget.** One probe, three bodies, same prompt and same
    model (`anthropic/claude-sonnet-5`):

    | body | `reasoning_tokens` billed | `content` |
    |---|---|---|
    | no `reasoning` parameter | 3811 | present |
    | `reasoning: {"max_tokens": 2000}` | **6233** — 3× the bound | present |
    | `reasoning: {"enabled": false}` | **0** | present, 1432 completion tokens |

    So the bound is not enforced and the off switch is. `ART_THINKING` defaults to off, and the
    turn is now structurally incapable of spending its budget before it writes anything.

    Two things this corrects in what was written here before. Sending no `reasoning` parameter
    was called right because "a flag suppressing it would be a guess at the cause of a fixed
    symptom" — the symptom was not fixed, and the cause is now measured rather than guessed.
    And the returned `reasoning` string is **not** the size of the thinking: 4418 characters
    against 3811 billed tokens, ~1.2 chars per token, which is why the char counts above read as
    if there was budget left when there was none.

    The trade is real and it is the cheaper side: a turn that cannot deliberate may pick a duller
    subject, and `TH-GROUND`, `TH-MARKS`, `TH-STYLE`, `TH-LAYOUT` and `TH-LABELS` all reject a bad
    one before an image is bought, at one text call each. A turn that deliberates itself out of
    answering costs a whole render attempt and cannot be checked at all.
    """
    return await _chat(
        prompt,
        model=model or DEFAULT_TEXT_MODEL,
        max_tokens=max_tokens,
        timeout=VISION_TIMEOUT,
        reasoning=None if ART_THINKING else {"enabled": False},
    )


async def ask_about_image(
    prompt: str,
    image_bytes: bytes,
    *,
    model: str = "",
    media_type: str = "image/png",
    max_tokens: int = 300,
) -> tuple[str, float]:
    """One vision question about one image. Returns `(answer, cost_usd)`.

    The image goes as a base64 data URL rather than a hosted URL on purpose: at the
    moment this runs, the cover has not been uploaded anywhere. Asking about the bytes
    in hand is also the only version of this check that is about the artifact that ships
    (AGENTS.md rule 29).
    """
    url = f"data:{media_type};base64,{base64.b64encode(image_bytes).decode()}"
    return await _chat(
        [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": url}},
        ],
        model=model or DEFAULT_VISION_MODEL,
        max_tokens=max_tokens,
        timeout=VISION_TIMEOUT,
    )


async def transcribe(
    image_bytes: bytes,
    *,
    model: str = "",
    media_type: str = "image/png",
) -> tuple[str, float]:
    """Read the text in an image back out. Returns `(text, cost_usd)`.

    A thin `ask_about_image` with the one prompt whose answer is compared by string
    equality — kept as its own name because it is a *gate* and the caller reads it as
    one, while `ask_about_image` is transport.
    """
    # 500, up from 300 when the reply became two groups. Measured, not padded: the longest
    # real transcript in the 4 Sep run was `recursion` attempt 3, ~150 characters of blueprint
    # annotation on one line, and a MARKS group now carries all of that plus the TEXT line's
    # own label. A truncated reply here fails the headline check on a correct cover, which is
    # the expensive direction.
    return await ask_about_image(
        TRANSCRIBE_PROMPT, image_bytes, model=model, media_type=media_type, max_tokens=500
    )


async def spell_back(
    image_bytes: bytes,
    *,
    model: str = "",
    media_type: str = "image/png",
) -> tuple[str, float]:
    """Read the headline's glyphs back one at a time. Returns `(spelled, cost_usd)`.

    Its own name for the same reason `transcribe` has one: it is a gate, and the caller
    compares its answer rather than reading it. See `SPELL_PROMPT` for the defect it exists
    for — a ligature that `transcribe` autocompleted into the word it expected.

    600 tokens rather than 300: one space per character roughly triples the reply, and a
    truncated spelling would fail the comparison as a mismatch, i.e. report a defect in the
    picture that is really a defect in the cap.
    """
    return await ask_about_image(
        SPELL_PROMPT, image_bytes, model=model, media_type=media_type, max_tokens=600
    )
