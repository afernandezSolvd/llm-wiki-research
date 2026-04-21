"""Unit tests for wiki diff output parser."""
from app.llm.output_parsers.wiki_diff import parse_ingest_tool_calls


def test_parse_edit_wiki_page():
    tool_calls = [
        {
            "name": "edit_wiki_page",
            "input": {
                "page_path": "pages/entities/openai.md",
                "title": "OpenAI",
                "page_type": "entity",
                "content": "# OpenAI\n\nAn AI company.",
                "change_summary": "Initial page",
            },
        }
    ]
    result = parse_ingest_tool_calls(tool_calls)
    assert len(result.page_edits) == 1
    assert result.page_edits[0].page_path == "pages/entities/openai.md"
    assert result.page_edits[0].title == "OpenAI"


def test_parse_kg_entities():
    tool_calls = [
        {
            "name": "add_kg_entities",
            "input": {
                "entities": [
                    {"name": "OpenAI", "type": "org", "aliases": ["Open AI"]},
                    {"name": "Sam Altman", "type": "person"},
                ],
                "relations": [
                    {"source": "Sam Altman", "target": "OpenAI", "relation": "works_at", "confidence": 0.95}
                ],
            },
        }
    ]
    result = parse_ingest_tool_calls(tool_calls)
    assert len(result.kg_entities) == 2
    assert result.kg_entities[0].name == "OpenAI"
    assert result.kg_entities[0].aliases == ["Open AI"]
    assert len(result.kg_relations) == 1
    assert result.kg_relations[0].confidence == 0.95


def test_parse_mixed_tools():
    tool_calls = [
        {"name": "edit_wiki_page", "input": {
            "page_path": "pages/entities/test.md",
            "title": "Test", "page_type": "entity",
            "content": "# Test", "change_summary": "test",
        }},
        {"name": "add_kg_entities", "input": {
            "entities": [{"name": "Test", "type": "concept"}], "relations": []
        }},
    ]
    result = parse_ingest_tool_calls(tool_calls)
    assert len(result.page_edits) == 1
    assert len(result.kg_entities) == 1


def test_parse_unknown_tool_ignored():
    tool_calls = [{"name": "unknown_tool", "input": {}}]
    result = parse_ingest_tool_calls(tool_calls)
    assert result.page_edits == []
    assert result.kg_entities == []
