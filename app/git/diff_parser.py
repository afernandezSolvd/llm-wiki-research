"""Parse unified diffs and compute semantic drift scores."""
import re


def extract_changed_lines(diff: str) -> tuple[list[str], list[str]]:
    """Return (removed_lines, added_lines) from a unified diff."""
    removed, added = [], []
    for line in diff.splitlines():
        if line.startswith("--- ") or line.startswith("+++ ") or line.startswith("@@"):
            continue
        if line.startswith("-"):
            removed.append(line[1:])
        elif line.startswith("+"):
            added.append(line[1:])
    return removed, added


def diff_is_meaningful(diff: str, min_changed_lines: int = 3) -> bool:
    """Return True if the diff has meaningful changes (not just whitespace)."""
    removed, added = extract_changed_lines(diff)
    non_trivial = [l for l in removed + added if l.strip()]
    return len(non_trivial) >= min_changed_lines


def extract_wikilinks(content: str) -> list[str]:
    """Extract [[target]] style wikilinks from markdown content."""
    return re.findall(r"\[\[([^\]]+)\]\]", content)
