"""Unit tests for consistency lint parsing and evidence builder."""
import json
import pytest

from app.llm.output_parsers.lint_findings import parse_lint_response, LLMLintFinding


def test_parse_consistency_type():
    payload = json.dumps([{
        "type": "consistency",
        "severity": "error",
        "description": "Conflicting Redis port numbers.",
        "topic": "Redis port",
        "page_a_excerpt": "Redis runs on port 6379",
        "page_b_excerpt": "Redis is configured on port 6380",
    }])
    findings = parse_lint_response(payload)
    assert len(findings) == 1
    assert findings[0].finding_type == "consistency"
    assert findings[0].topic == "Redis port"


def test_parse_topic_field():
    payload = json.dumps([{
        "type": "consistency",
        "severity": "warning",
        "description": "Conflicting values.",
        "page_a_excerpt": "value A",
        "page_b_excerpt": "value B",
    }])
    findings = parse_lint_response(payload)
    assert len(findings) == 1
    assert findings[0].topic == ""


def test_evidence_builder_structure():
    f = LLMLintFinding(
        finding_type="consistency",
        severity="error",
        description="Conflicting Redis port numbers.",
        topic="Redis port",
        page_a_excerpt="port 6379",
        page_b_excerpt="port 6380",
    )
    evidence = {
        "conflicting_pages": [
            {"path": "pages/entities/redis.md", "excerpt": f.page_a_excerpt},
            {"path": "pages/summaries/docker-compose-yml.md", "excerpt": f.page_b_excerpt},
        ],
        "topic": f.topic,
        "pair_source": "kg_community",
    }
    assert isinstance(evidence["conflicting_pages"], list)
    assert len(evidence["conflicting_pages"]) == 2
    assert evidence["topic"] == "Redis port"
