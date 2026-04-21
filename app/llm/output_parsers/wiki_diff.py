"""Parse LLM tool call responses for the ingest operation."""
from dataclasses import dataclass, field


@dataclass
class PageEdit:
    page_path: str
    title: str
    page_type: str
    content: str
    change_summary: str


@dataclass
class KGEntity:
    name: str
    entity_type: str
    aliases: list[str] = field(default_factory=list)


@dataclass
class KGRelation:
    source: str
    target: str
    relation: str
    confidence: float = 1.0


@dataclass
class IngestResult:
    page_edits: list[PageEdit] = field(default_factory=list)
    kg_entities: list[KGEntity] = field(default_factory=list)
    kg_relations: list[KGRelation] = field(default_factory=list)
    raw_text: str = ""


def parse_ingest_tool_calls(tool_calls: list[dict]) -> IngestResult:
    """Parse the LLM's tool use blocks into structured IngestResult."""
    result = IngestResult()

    for call in tool_calls:
        name = call.get("name", "")
        inp = call.get("input", {})

        if name == "edit_wiki_page":
            result.page_edits.append(
                PageEdit(
                    page_path=inp["page_path"],
                    title=inp["title"],
                    page_type=inp["page_type"],
                    content=inp["content"],
                    change_summary=inp.get("change_summary", ""),
                )
            )

        elif name == "add_kg_entities":
            for e in inp.get("entities", []):
                result.kg_entities.append(
                    KGEntity(
                        name=e["name"],
                        entity_type=e["type"],
                        aliases=e.get("aliases", []),
                    )
                )
            for r in inp.get("relations", []):
                result.kg_relations.append(
                    KGRelation(
                        source=r["source"],
                        target=r["target"],
                        relation=r["relation"],
                        confidence=float(r.get("confidence", 1.0)),
                    )
                )

    return result
