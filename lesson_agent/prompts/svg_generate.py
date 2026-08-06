"""
Prompt for SVG diagram generation.

Used by svg_agent.py to generate educational SVG diagrams
that are specific to the lesson concept being taught.
"""


def build_svg_generation_prompt(
    concept: str,
    context: str,
    audience: str = "learners",
    feedback: str | None = None,
) -> str:
    """Build the prompt that asks Claude to generate an educational SVG."""
    base = f"""Generate a clean, educational SVG diagram for this concept:

**Concept:** {concept}
**Context:** {context}
**Audience:** {audience}

## SVG Requirements:

1. Return ONLY the raw `<svg>...</svg>` — nothing else (no markdown, no explanation, no code fences)
2. **VALID XML — CRITICAL:** Every element must be well-formed. NEVER repeat an attribute on the same element (e.g. `<rect x="10" x="20">` is INVALID — each attribute appears ONCE). Close every tag. Quote every attribute value.
3. Use a LARGE canvas: `viewBox="0 0 1000 700"` — gives room to breathe (avoid cramping).

## ⚠️ NO OVERLAP — SPACING IS CRITICAL (the #1 quality rule):
Overlapping text/shapes make a diagram unreadable. Follow these STRICTLY:
- **Leave ≥ 30px of empty space between EVERY element** (shapes, text, arrows). Never let two things touch or overlap.
- **Boxes must fully contain their label** with ≥ 12px padding on all sides. Size the rectangle to fit the text — a 20-char label needs a box ≥ 200px wide.
- **Center text inside shapes** with BOTH `text-anchor="middle"` AND `dominant-baseline="middle"`, positioned at the shape's exact center (x = rectX + width/2, y = rectY + height/2).
- **Text NEVER straddles a shape edge or another text element.** If a label sits outside a shape, keep it ≥ 20px away from any border.
- **Keep labels SHORT** (≤ 20 characters). For longer text, split across lines using `<tspan x="..." dy="1.2em">` so lines stack vertically (never let a long label run off the edge).
- **Nothing touches the canvas border** — keep all content within a 40px inner margin (x: 40–960, y: 40–660).
- **Prefer FEWER, well-spaced elements** over many cramped ones. A clear 4-box diagram beats a crowded 10-box mess.
- Lay elements on an imaginary grid with generous, even gaps.

## Other requirements:
4. Include clear **text labels** for all important elements (a diagram without labels is useless)
5. Use arrows (lines with markers) to show relationships/flow — arrows must not cross through text
6. Clean color palette:
   - Background: white or light gray (#f8f9fa)
   - Primary shapes: #4A90D9 (blue), #50C878 (green), #FF6B6B (red/warning), #F5A623 (orange)
   - Text: #333333 (dark) — or #ffffff on dark-filled shapes for contrast
   - Arrows/lines: #666666
7. Make it EDUCATIONAL, attractive, and charismatic — the diagram should TEACH clearly AND look polished
8. Use meaningful shapes (rectangles = objects/steps, diamonds = decisions, circles = states, arrows = flow)
9. Font: `font-family="Arial, sans-serif"`, minimum `font-size="16"` for labels, `font-size="22"` bold for titles
10. Add a short title at the top and use rounded corners (`rx="8"`) on boxes for a modern look

## What makes a GOOD educational SVG:
- Zero overlaps — every element clearly separated with generous whitespace
- You understand the concept by looking ONLY at the diagram
- Specific labels (not "Step 1"), correct spatial layout (left→right = sequence, top→bottom = hierarchy)
- Visual hierarchy + polish (titles, consistent colors, rounded corners)

## What makes a BAD educational SVG (REJECTED):
- ANY overlapping text or shapes
- Text clipped at the canvas edge or running off the box
- Cramped elements with no breathing room
- Generic unlabeled shapes; labels unrelated to the concept
"""

    if feedback:
        base += f"""

## ⚠️ PREVIOUS ATTEMPT FEEDBACK (fix these issues):
{feedback}

Generate an IMPROVED version that addresses all the feedback above.
"""

    return base


def build_svg_review_prompt(svg_content: str, concept: str, context: str) -> str:
    """Build the prompt that asks Claude to review/judge a generated SVG."""
    return f"""Review this SVG diagram for educational quality.

**Concept it should teach:** {concept}
**Lesson context:** {context}

**The SVG:**
```xml
{svg_content}
```

(Note: element spacing/overlap is already checked separately by a geometric tool —
focus your judgment on MEANING and correctness, not pixel positions.)

Score it 1-10 on each dimension:
- **Relevance** (1-10): Does it specifically illustrate THIS concept (not something generic)?
- **Clarity** (1-10): Can a learner understand it without additional explanation?
- **Labels** (1-10): Are elements properly labeled with concept-specific, correct terms?
- **Accuracy** (1-10): Is the information correct and not misleading? Does it faithfully represent the concept?

**Overall score** = average of the 4 scores (round to nearest integer).

If overall score < 7, list exactly what's wrong and how to fix it (focus on relevance/clarity/accuracy — NOT spacing).

Respond in this exact format:
RELEVANCE: [score]
CLARITY: [score]
LABELS: [score]
ACCURACY: [score]
OVERALL: [score]
ISSUES: [comma-separated list of issues, or "none"]
"""
