"""Prompts for the query / synthesis operation."""

QUERY_SYSTEM = """\
You are a knowledge base assistant. Answer questions using only the provided wiki context \
and source excerpts. Be accurate, concise, and cite your sources.

Citation format: use [page_title](page_path) for wiki pages and [Source: title] for raw sources.
If the context does not contain enough information to answer, say so clearly.
Do not hallucinate facts not present in the context.
"""

QUERY_USER_TEMPLATE = """\
<question>
${question}
</question>

<context>
${context}
</context>

Answer the question based on the context above. Include citations.
"""
