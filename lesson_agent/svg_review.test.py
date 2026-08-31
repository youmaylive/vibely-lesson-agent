#!/usr/bin/env python3
"""
Executable expectations for `svg_agent.parse_review_response`.

This file exists because the parse had NO cases: it was welded into the body of the
async `_review_svg`, so exercising one line of regex cost a Bedrock call. Rule 18's
shape on a judge rather than a validator — the review scores were trusted for months
and the thing producing them had never been run against a known input.

What it was hiding, found by reading a real run's log (`/tmp/full_probe.log`) rather
than the code: `grounding` came back as *exactly* 6 on **10 of 12** attempts across
three independent figures. 6 is `REVIEW_THRESHOLD - 1`, i.e. the output of a clamp, not
a judgement — a model's own opinion does not land on one integer ten times. The clamp
read the review's **overall** VERDICT and treated FAIL as evidence of a *grounding*
failure, inverting the prompt's one-directional rule ("if Grounding < 7, VERDICT is
FAIL", `prompts/svg_generate.py:151`). Since the grounding gate `continue`s before the
ranking key is computed, every clamped candidate was discarded instead of ranked, and
the geometry-clean draft of figure 0 was thrown away in favour of one that shipped with
STATIC_STRUCTURE, TEXT_OVERFLOWS_RECT and TEXT_SPILL.

Stdlib only, no pytest, no network, no credentials — it must run identically on a Mac
and inside the worker image, where `lesson_agent` is flattened to `/app/lesson-agent/*.py`
(so `import svg_agent`, never `import lesson_agent.svg_agent`).

    python3 svg_review.test.py                 # everything
    python3 svg_review.test.py clamp           # only cases matching a substring
    python3 svg_review.test.py --list

    # in the worker image, before pushing (rule 22):
    docker run --rm --entrypoint python3 memebu-worker:latest \
      /app/lesson-agent/svg_review.test.py

Note the cases assert the *reason* a number came out, not just the number: several
inputs can produce `grounding == 6` for entirely different reasons, and a case that only
checked the 6 would have passed on the bug it was written to catch.
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import svg_agent as S  # noqa: E402

CASES: list[tuple[str, object, str | None]] = []


def case(name: str, xfail: str | None = None):
    def wrap(fn):
        CASES.append((name, fn, xfail))
        return fn

    return wrap


def eq(actual, expected, what: str) -> None:
    if actual != expected:
        raise AssertionError(f"{what}: expected {expected!r}, got {actual!r}")


def true(cond, what: str) -> None:
    if not cond:
        raise AssertionError(what)


def parse(response: str, *, excerpt: bool = True):
    """Call the parser with stdout captured, and return (score, issues, grounding, out).

    The REVIEW_UNAVAILABLE branch prints; swallowing it keeps a test run readable, and
    returning it lets the cases assert the warning actually fired (rule 21 — a gate
    that cannot run must say so, and "it says so" is itself worth pinning).
    """
    buf = io.StringIO()
    with redirect_stdout(buf):
        score, issues, grounding = S.parse_review_response(response, has_excerpt=excerpt)
    return score, issues, grounding, buf.getvalue()


# A complete, well-formed reviewer response in the exact shape the prompt asks for
# (`prompts/svg_generate.py:202-212`). Written from that template, not from memory:
# a fixture invented from a remembered format is how a suite ends up testing nothing.
def review(*, overall: int, grounding: int | None, verdict: str, issues: str = "none") -> str:
    g = "" if grounding is None else f"GROUNDING: {grounding}\n"
    return (
        "RELEVANCE: 8\n"
        "CLARITY: 7\n"
        "LABELS: 6\n"
        "ACCURACY: 8\n"
        "CRAFT: 5\n"
        "DENSITY: 6\n"
        "POLISH: 4\n"
        f"{g}OVERALL: {overall}\n"
        f"VERDICT: {verdict}\n"
        f"ISSUES: {issues}\n"
    )


# ---------------------------------------------------------------------------
# The regression: an overall FAIL is not a grounding failure
# ---------------------------------------------------------------------------

@case("clamp: overall FAIL with a high numeric GROUNDING does not clamp")
def _() -> None:
    # THE bug, in one case. A faithful diagram with flat fills and wordy labels scores
    # 6 overall and correctly reports VERDICT: FAIL for that reason. Its grounding is 9
    # and must survive, or the caller discards a candidate for a defect it does not have.
    score, _, grounding, _ = parse(review(overall=6, grounding=9, verdict="FAIL"))
    eq(score, 6, "overall score")
    eq(grounding, 9, "grounding must be the model's own number, not REVIEW_THRESHOLD - 1")
    true(
        grounding >= S.REVIEW_THRESHOLD,
        "a grounded candidate must clear the hard gate so it can be RANKED; "
        "before the fix this returned 6 and was dropped by `continue` before the "
        "ranking key was ever computed",
    )


@case("clamp: overall FAIL with a LOW numeric GROUNDING still fails the gate")
def _() -> None:
    # The other direction, and the reason the gate exists at all: a polished diagram
    # that invents values scored 8/10 and shipped. Keep that closed.
    _, _, grounding, _ = parse(review(overall=6, grounding=2, verdict="FAIL"))
    eq(grounding, 2, "a real grounding failure is reported as itself")
    true(grounding < S.REVIEW_THRESHOLD, "a hallucinated diagram must not clear the gate")


@case("clamp: overall PASS with a low numeric GROUNDING is still a grounding failure")
def _() -> None:
    # The prompt's rule is one-directional, and the model may simply not apply it.
    # The numeric line is the authority either way.
    _, _, grounding, _ = parse(review(overall=8, grounding=3, verdict="PASS"))
    eq(grounding, 3, "PASS does not launder a low grounding score")


@case("clamp: fires only as a FALLBACK, when the numeric line is absent")
def _() -> None:
    # This is what the clamp was FOR: the model garbled or forgot the numeric line but
    # said FAIL. With nothing to read, a conservative 6 is right — refusing a candidate
    # costs one retry, accepting an unmeasured one is the original bug.
    _, _, grounding, _ = parse(review(overall=6, grounding=None, verdict="FAIL"))
    eq(grounding, S.REVIEW_THRESHOLD - 1, "no numeric line + FAIL clamps")


@case("clamp: no numeric line and PASS is trusted at 10")
def _() -> None:
    _, _, grounding, _ = parse(review(overall=8, grounding=None, verdict="PASS"))
    eq(grounding, 10, "nothing to contradict the verdict")


@case("clamp: the real run's shape — 6 for the right reason vs the wrong one")
def _() -> None:
    # Two inputs, both of which USED to return 6. A case asserting only the number
    # would have passed on the bug. Assert that they now differ.
    was_bug = parse(review(overall=6, grounding=9, verdict="FAIL"))[2]
    is_real = parse(review(overall=6, grounding=None, verdict="FAIL"))[2]
    true(
        was_bug != is_real,
        f"both paths still collapse to {was_bug}; the clamp is not distinguishing "
        "'the model judged it ungrounded' from 'the model failed it for craft'",
    )


# ---------------------------------------------------------------------------
# Grounding parse, generally
# ---------------------------------------------------------------------------

@case("grounding: 10 when no excerpt was supplied, whatever the verdict says")
def _() -> None:
    # There is nothing to be unfaithful to, so the gate must not fire. Callers gate on
    # this unconditionally, per `_review_svg`'s docstring.
    _, _, grounding, _ = parse(review(overall=4, grounding=2, verdict="FAIL"), excerpt=False)
    eq(grounding, 10, "no excerpt = no grounding gate")


@case("grounding: markdown bold and a /10 suffix parse")
def _() -> None:
    _, _, grounding, _ = parse("**GROUNDING:** 9/10\nOVERALL: 7\nVERDICT: PASS\nISSUES: none")
    eq(grounding, 9, "**GROUNDING:** 9/10")


@case("grounding: a float rounds")
def _() -> None:
    _, _, grounding, _ = parse("GROUNDING: 6.5\nOVERALL: 7\nVERDICT: PASS")
    eq(grounding, 6, "6.5 rounds to 6 (banker's rounding — pinned, not asserted as ideal)")


@case("grounding: prose before the number is tolerated within the 20-char window")
def _() -> None:
    _, _, grounding, _ = parse("Grounding score is 8\nOVERALL: 7\nVERDICT: PASS")
    eq(grounding, 8, "'Grounding score is 8'")


# ---------------------------------------------------------------------------
# Score parse
# ---------------------------------------------------------------------------

@case("score: OVERALL wins over the dimension average")
def _() -> None:
    score, _, _, _ = parse(review(overall=9, grounding=9, verdict="PASS"))
    eq(score, 9, "the explicit OVERALL line is authoritative")


@case("score: falls back to averaging the dimensions when OVERALL is missing")
def _() -> None:
    # RELEVANCE 8, CLARITY 7, LABELS 6, ACCURACY 8, CRAFT 5, DENSITY 6, POLISH 4,
    # GROUNDING 9 -> 53/8 = 6.625 -> 7.
    body = review(overall=0, grounding=9, verdict="PASS").replace("OVERALL: 0\n", "")
    score, _, _, _ = parse(body)
    eq(score, 7, "average of the 8 dimensions present")


@case("score: None (REVIEW_UNAVAILABLE) when fewer than 3 dimensions are present")
def _() -> None:
    # "averaging 1 stray number is not a judgement" — and it must SAY it could not run,
    # rather than defaulting to a borderline 7 as it once did (rule 21).
    score, _, _, out = parse("This diagram looks fine to me. 8 out of 10 stars, I guess.")
    eq(score, None, "unparseable review")
    true("REVIEW_UNAVAILABLE" in out, f"the warning must be printed; got {out!r}")


@case("score: an empty response is unavailable, not a zero")
def _() -> None:
    score, _, _, out = parse("")
    eq(score, None, "empty response")
    true("REVIEW_UNAVAILABLE" in out, "silence is not a pass")


# ---------------------------------------------------------------------------
# Issues parse
# ---------------------------------------------------------------------------

@case("issues: the list is extracted and stripped of markdown")
def _() -> None:
    _, issues, _, _ = parse(review(overall=5, grounding=9, verdict="FAIL",
                                   issues="labels overlap, flat fills"))
    eq(issues, "labels overlap, flat fills", "ISSUES line")


@case("issues: empty string when the line is absent")
def _() -> None:
    _, issues, _, _ = parse("OVERALL: 8\nGROUNDING: 8\nVERDICT: PASS")
    eq(issues, "", "no ISSUES line")


# ---------------------------------------------------------------------------
# The contract this parser has with the prompt (rule 26: a rule the prompt states
# and nothing checks is a regression no test catches)
# ---------------------------------------------------------------------------

@case("contract: every dimension the prompt asks for is in the averaging fallback")
def _() -> None:
    # If a dimension is added to the review prompt and not here, the fallback average
    # silently drops it and skews toward the rest — the exact comment above that tuple.
    # So derive the expectation from the PROMPT, not from a second hand-written list.
    from prompts.svg_generate import build_svg_review_prompt

    prompt = build_svg_review_prompt("<svg/>", "c", "ctx", lesson_excerpt="e")
    asked = {
        line.split(":")[0].strip().lower()
        for line in prompt.splitlines()
        if line.strip().endswith("[score]") and ":" in line
    }
    true(len(asked) >= 8, f"expected the response template to list the dimensions, saw {asked}")
    src = Path(__file__).resolve().parent.joinpath("svg_agent.py").read_text()
    block = src.split('for dim in (', 1)[1].split(')', 1)[0].lower()
    missing = sorted(d for d in asked if d not in block and d != "overall")
    eq(missing, [], "dimensions asked for by the prompt but absent from the fallback average")


@case("contract: the prompt's grounding rule really is one-directional")
def _() -> None:
    # The fix rests on this reading. Pin it, so that if someone later makes the prompt
    # emit a grounding-scoped verdict, this case fails and points at the parser.
    from prompts.svg_generate import build_svg_review_prompt

    prompt = build_svg_review_prompt("<svg/>", "c", "ctx", lesson_excerpt="e")
    true(
        "if Grounding < 7, VERDICT is FAIL" in prompt,
        "the prompt states grounding-fail => verdict-FAIL; the parser must not read it backwards",
    )
    true(
        "GROUNDING: [score]" in prompt,
        "an excerpt was supplied, so a numeric grounding line is requested and the "
        "verdict clamp should be a rarely-taken fallback",
    )


@case("contract: no excerpt means the prompt asks for no grounding at all")
def _() -> None:
    from prompts.svg_generate import build_svg_review_prompt

    prompt = build_svg_review_prompt("<svg/>", "c", "ctx", lesson_excerpt="")
    true("GROUNDING" not in prompt.upper(), "nothing to be faithful to, so no grounding dimension")


def run(filters: list[str]) -> int:
    selected = [
        (name, fn, xf)
        for name, fn, xf in CASES
        if not filters or any(f.lower() in name.lower() for f in filters)
    ]

    passed = failed = xfailed = xpassed = 0
    failures: list[tuple[str, str]] = []

    for name, fn, xf in selected:
        try:
            fn()
        except AssertionError as exc:
            if xf:
                xfailed += 1
                print(f"  xfail {name}  ({exc})")
            else:
                failed += 1
                failures.append((name, str(exc)))
                print(f"  FAIL  {name}\n        {exc}")
            continue
        except Exception:
            import traceback

            detail = traceback.format_exc(limit=3).strip().splitlines()[-1]
            if xf:
                xfailed += 1
                print(f"  xfail {name}  ({detail})")
            else:
                failed += 1
                failures.append((name, detail))
                print(f"  ERROR {name}\n        {detail}")
            continue

        if xf:
            xpassed += 1
            print(f"  XPASS {name}  <- fixed; drop the xfail marker")
        else:
            passed += 1
            print(f"  ok    {name}")

    print(f"\n{passed} passed, {failed} failed, {xfailed} xfail, {xpassed} xpass")
    if xpassed:
        print(f"\n{xpassed} case(s) now pass that were marked xfail. Remove the marker.")
    if failures:
        print("\nFailures:")
        for name, msg in failures:
            print(f"  - {name}: {msg}")
        return 1
    return 0


def main(argv: list[str]) -> int:
    if "--list" in argv:
        for name, _, xf in CASES:
            print(f"{'xfail' if xf else '     '} {name}")
        return 0
    return run([a for a in argv if not a.startswith("-")])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
