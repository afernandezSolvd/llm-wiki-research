"""Parse lint LLM response into structured findings."""
import json
import re
from dataclasses import dataclass, field


@dataclass
class LLMLintFinding:
    finding_type: str
    severity: str
    description: str
    page_a_excerpt: str = ""
    page_b_excerpt: str = ""


def parse_lint_response(text: str) -> list[LLMLintFinding]:
    """Extract JSON array of findings from LLM response."""
    # Find JSON array in the response
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []

    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []

    findings = []
    for item in items:
        if not isinstance(item, dict):
            continue
        findings.append(
            LLMLintFinding(
                finding_type=item.get("type", "contradiction"),
                severity=item.get("severity", "warning"),
                description=item.get("description", ""),
                page_a_excerpt=item.get("page_a_excerpt", ""),
                page_b_excerpt=item.get("page_b_excerpt", ""),
            )
        )
    return findings
