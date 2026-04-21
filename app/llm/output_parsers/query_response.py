"""Parse query LLM response into structured answer + citations."""
import re
from dataclasses import dataclass, field


@dataclass
class Citation:
    title: str
    page_path: str | None = None
    source_title: str | None = None


@dataclass
class QueryAnswer:
    answer_text: str
    citations: list[Citation] = field(default_factory=list)


def parse_query_response(text: str) -> QueryAnswer:
    """Extract citations from markdown-formatted answer text."""
    # Match [Title](path) style wiki citations
    wiki_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    # Match [Source: title] style source citations
    source_pattern = re.compile(r"\[Source:\s*([^\]]+)\]")

    citations: list[Citation] = []
    seen: set[str] = set()

    for match in wiki_pattern.finditer(text):
        title, path = match.group(1), match.group(2)
        key = f"wiki:{path}"
        if key not in seen:
            citations.append(Citation(title=title, page_path=path))
            seen.add(key)

    for match in source_pattern.finditer(text):
        title = match.group(1).strip()
        key = f"source:{title}"
        if key not in seen:
            citations.append(Citation(title=title, source_title=title))
            seen.add(key)

    return QueryAnswer(answer_text=text, citations=citations)
