"""Prompts and tool definitions for the ingest operation."""

INGEST_SYSTEM = """\
You are a wiki maintenance agent. Your job is to update a structured knowledge wiki \
based on new source material.

Given source content, you will:
1. Identify key entities, concepts, and facts
2. Decide which existing wiki pages need updating and what new pages should be created
3. Write high-quality, concise markdown for each page change
4. Extract entity relationships for the knowledge graph
5. Update the wiki index and log

Rules:
- Only include information supported by the source. Do not hallucinate.
- Preserve existing accurate content when updating pages; only change what the source adds or corrects.
- Use [[page_path]] syntax to cross-reference other wiki pages.
- Each entity page must include: description, key attributes, related entities.
- Mark claims with source references like: (source: {source_title}).
- Be conservative: fewer high-quality edits beat many shallow ones.
"""

INGEST_USER_TEMPLATE = """\
<source>
Title: ${title}
Type: ${source_type}
Content:
${content}
</source>

<current_wiki_context>
${wiki_context}
</current_wiki_context>

Review the source and update the wiki accordingly. Use the provided tools to:
1. Create or update wiki pages
2. Record entity relationships in the knowledge graph
3. Update index.md if new pages are created
4. Append a summary entry to log.md
"""

# Tool definitions for structured LLM output
INGEST_TOOLS = [
    {
        "name": "edit_wiki_page",
        "description": "Create or update a wiki page with new content.",
        "input_schema": {
            "type": "object",
            "required": ["page_path", "title", "page_type", "content", "change_summary"],
            "properties": {
                "page_path": {
                    "type": "string",
                    "description": "Relative path e.g. 'pages/entities/openai.md'",
                },
                "title": {"type": "string"},
                "page_type": {
                    "type": "string",
                    "enum": ["entity", "concept", "summary", "exploration", "index", "log"],
                },
                "content": {
                    "type": "string",
                    "description": "Full markdown content for the page",
                },
                "change_summary": {
                    "type": "string",
                    "description": "One-line description of what changed and why",
                },
            },
        },
    },
    {
        "name": "add_kg_entities",
        "description": "Record entities and relationships extracted from the source.",
        "input_schema": {
            "type": "object",
            "required": ["entities"],
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "type"],
                        "properties": {
                            "name": {"type": "string"},
                            "type": {
                                "type": "string",
                                "enum": ["person", "org", "concept", "technology", "event", "place"],
                            },
                            "aliases": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                },
                "relations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["source", "target", "relation"],
                        "properties": {
                            "source": {"type": "string"},
                            "target": {"type": "string"},
                            "relation": {
                                "type": "string",
                                "enum": [
                                    "works_at", "founded", "acquired", "uses",
                                    "related_to", "contradicts", "part_of", "created",
                                ],
                            },
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                    },
                },
            },
        },
    },
]
