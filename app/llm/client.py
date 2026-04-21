"""Anthropic SDK client singleton with prompt caching support."""
from functools import lru_cache

import anthropic

from app.config import get_settings

settings = get_settings()


@lru_cache
def get_anthropic_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def make_cached_block(text: str) -> dict:
    """Wrap a text string as a cache-eligible content block."""
    return {
        "type": "text",
        "text": text,
        "cache_control": {"type": "ephemeral"},
    }


def make_text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def extract_usage(response: anthropic.types.Message) -> dict:
    """Extract token usage including cache stats from a response."""
    u = response.usage
    return {
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0),
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0),
    }


def estimate_cost_usd(usage: dict) -> float:
    """Estimate cost in USD for claude-opus-4-6 pricing (approximate)."""
    # Input: $15/MTok, Cache write: $18.75/MTok, Cache read: $1.50/MTok, Output: $75/MTok
    input_cost = usage["input_tokens"] / 1_000_000 * 15.0
    cache_write_cost = usage["cache_creation_input_tokens"] / 1_000_000 * 18.75
    cache_read_cost = usage["cache_read_input_tokens"] / 1_000_000 * 1.50
    output_cost = usage["output_tokens"] / 1_000_000 * 75.0
    return input_cost + cache_write_cost + cache_read_cost + output_cost
