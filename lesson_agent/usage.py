"""Process-wide token/cost accumulator for one lesson-agent run.

Why this module exists
----------------------
The curriculum worker runs this package as a *subprocess* and reads its spend off
stdout as a ``##USAGE:...##`` marker. That marker was hardcoded to
``total_cost=0:input_tokens=0:output_tokens=0``, and nothing on the worker side
had ever parsed it — so the MLAI phase, by far the largest single cost in a course
run (~46 lessons plus every SVG generate/review call), was reported to
``usage_records`` as zero spend and zero tokens.

Spend arrives from two unrelated places that must not import each other:

* ``agent.py`` — Claude Agent SDK ``ResultMessage.usage`` (a dict), per lesson.
* ``svg_agent.py`` — a direct Bedrock ``messages.create`` response (``resp.usage``,
  an object), per SVG generate/review call.

Rather than thread return values through ``generate_lesson`` /
``generate_curriculum`` / ``resolve_svgs`` / ``generate_one_svg``, both record into
this one flat module. Stdlib only, no SDK import, so it is safe for either side to
import and testable with no credentials.

Cache tokens
------------
``add_sdk_usage`` counts ``cache_creation_input_tokens`` and
``cache_read_input_tokens`` as input. For a cached agentic run these dominate the
plain ``input_tokens`` field, so omitting them undercounts substantially. Note the
pre-existing extractors in ``memebu-lesson-planner``'s ``agent_v2.py`` and
``memebu-ontology-engine``'s ``agent.py`` read only the two plain keys and therefore
undercount; they are deliberately left alone here so the ontology and spine numbers
do not shift under the same deploy.
"""

from __future__ import annotations

import os
from threading import Lock

_lock = Lock()

total_cost_usd: float = 0.0
input_tokens: int = 0
output_tokens: int = 0
api_calls: int = 0

# Input-token keys on the SDK's usage dict. Cache reads/creations are real input
# tokens billed at a different rate; the cost field already accounts for the rate,
# so for a token *count* they simply add.
_INPUT_KEYS = (
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def _as_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def record(
    *,
    cost_usd: float = 0.0,
    input_tokens_delta: int = 0,
    output_tokens_delta: int = 0,
    calls: int = 1,
) -> None:
    """Add one API call's usage to the running totals."""
    global total_cost_usd, input_tokens, output_tokens, api_calls
    with _lock:
        total_cost_usd += float(cost_usd or 0.0)
        input_tokens += _as_int(input_tokens_delta)
        output_tokens += _as_int(output_tokens_delta)
        api_calls += _as_int(calls)


def add_sdk_usage(usage, cost_usd: float = 0.0, calls: int = 1) -> None:
    """Record usage from a Claude Agent SDK ``ResultMessage``.

    ``usage`` is a plain dict (``ResultMessage.usage``); tolerates None so a result
    without usage still books its cost.
    """
    data = usage if isinstance(usage, dict) else {}
    record(
        cost_usd=cost_usd,
        input_tokens_delta=sum(_as_int(data.get(k)) for k in _INPUT_KEYS),
        output_tokens_delta=_as_int(data.get("output_tokens")),
        calls=calls,
    )


# Sonnet-class on-demand Bedrock rates, USD per million tokens. Cache reads bill
# at a tenth of input, but are counted here at the full input rate: overpricing a
# cache hit is the safe direction, and the alternative is what we had — $0.00.
# Override both via env when the rate card or model changes.
_USD_PER_M_INPUT = float(os.environ.get("BEDROCK_USD_PER_M_INPUT", "3.0"))
_USD_PER_M_OUTPUT = float(os.environ.get("BEDROCK_USD_PER_M_OUTPUT", "15.0"))


def estimate_cost(input_tokens_delta: int, output_tokens_delta: int) -> float:
    """Price Bedrock tokens, which arrive without a cost field."""
    return (
        _as_int(input_tokens_delta) / 1_000_000 * _USD_PER_M_INPUT
        + _as_int(output_tokens_delta) / 1_000_000 * _USD_PER_M_OUTPUT
    )


def add_bedrock_usage(usage, calls: int = 1) -> None:
    """Record usage from a Bedrock ``messages.create`` response.

    ``resp.usage`` is an object with attributes, not a dict, and carries **no cost**
    field — Bedrock bills per token and the SDK does no arithmetic for us. So the
    cost is derived from the token counts at the rates above, rather than left at
    zero: measured on one real diagram this path is ~39k in / 14k out tokens
    (~$0.33), i.e. roughly $30 per 46-lesson course that previously reached
    usage_records as $0.00. An estimate at a stated rate beats a known-wrong zero.
    """
    if usage is None:
        return
    input_delta = sum(_as_int(getattr(usage, k, 0)) for k in _INPUT_KEYS)
    output_delta = _as_int(getattr(usage, "output_tokens", 0))
    record(
        cost_usd=estimate_cost(input_delta, output_delta),
        input_tokens_delta=input_delta,
        output_tokens_delta=output_delta,
        calls=calls,
    )


def snapshot() -> dict:
    """Current totals."""
    with _lock:
        return {
            "total_cost": total_cost_usd,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "api_calls": api_calls,
        }


def marker(extra_api_calls: int = 0) -> str:
    """Render the ``##USAGE:...##`` line parsed by the curriculum worker.

    Field names and the ``key=value`` colon format must stay in sync with
    ``memebu-engine-v2/workers/phases/curriculum.py``'s ``parse_usage_marker``.
    """
    snap = snapshot()
    calls = snap["api_calls"] + max(0, int(extra_api_calls or 0))
    return (
        f"##USAGE:total_cost={snap['total_cost']:.6f}"
        f":input_tokens={snap['input_tokens']}"
        f":output_tokens={snap['output_tokens']}"
        f":api_calls={calls}##"
    )


def reset() -> None:
    """Zero the totals (tests only)."""
    global total_cost_usd, input_tokens, output_tokens, api_calls
    with _lock:
        total_cost_usd = 0.0
        input_tokens = 0
        output_tokens = 0
        api_calls = 0
