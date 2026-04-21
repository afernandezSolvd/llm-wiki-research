"""Prompts for the lint / health-check operation."""

LINT_SYSTEM = """\
You are a wiki quality reviewer. Given two wiki pages, identify any factual contradictions \
between them. Be precise: cite exact sentences that conflict.

Output a JSON array of findings (empty array if no contradictions):
[
  {
    "type": "contradiction",
    "severity": "error" | "warning",
    "description": "concise description of the contradiction",
    "page_a_excerpt": "relevant sentence from page A",
    "page_b_excerpt": "conflicting sentence from page B"
  }
]

Only report clear factual contradictions, not differences in emphasis or framing.
"""

LINT_USER_TEMPLATE = """\
<page_a path="${path_a}" title="${title_a}">
${content_a}
</page_a>

<page_b path="${path_b}" title="${title_b}">
${content_b}
</page_b>

Identify contradictions between these two pages.
"""
