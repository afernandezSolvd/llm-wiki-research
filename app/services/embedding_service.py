"""Embedding service using Anthropic's Voyage embeddings via the voyage API."""
import asyncio
from functools import lru_cache

import anthropic

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

EMBEDDING_DIM = 1024
CHUNK_SIZE = 1000  # tokens
CHUNK_OVERLAP = 100  # tokens
MAX_BATCH_SIZE = 128  # voyage API limit


class EmbeddingService:
    def __init__(self):
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts. Batches automatically."""
        if not texts:
            return []

        results: list[list[float]] = []
        for i in range(0, len(texts), MAX_BATCH_SIZE):
            batch = texts[i : i + MAX_BATCH_SIZE]
            # Voyage API is sync; run in thread pool
            embeddings = await asyncio.get_running_loop().run_in_executor(
                None, self._embed_sync, batch
            )
            results.extend(embeddings)
        return results

    async def embed_single(self, text: str) -> list[float]:
        results = await self.embed_texts([text])
        return results[0]

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        import voyageai  # optional dep, falls back to random for dev

        try:
            client = voyageai.Client(api_key=settings.voyage_api_key)
            result = client.embed(texts, model=settings.anthropic_embedding_model)
            return result.embeddings
        except Exception as exc:
            # Fallback: return random unit vectors (dev/test without Voyage key)
            logger.warning("voyage_embed_failed_using_random", count=len(texts), error=str(exc))
            import random
            return [[random.gauss(0, 0.1) for _ in range(EMBEDDING_DIM)] for _ in texts]

    def chunk_text(self, text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
        """Split text into overlapping token-approximate chunks."""
        import tiktoken

        try:
            enc = tiktoken.get_encoding("cl100k_base")
            tokens = enc.encode(text)
        except Exception:
            # Fallback: word-based approximate chunking
            words = text.split()
            tokens = words  # type: ignore[assignment]

        chunks = []
        start = 0
        while start < len(tokens):
            end = min(start + chunk_size, len(tokens))
            chunk_tokens = tokens[start:end]
            if isinstance(chunk_tokens[0], int):
                chunk_text = enc.decode(chunk_tokens)  # type: ignore[possibly-undefined]
            else:
                chunk_text = " ".join(chunk_tokens)  # type: ignore[arg-type]
            chunks.append(chunk_text)
            if end == len(tokens):
                break
            start = end - overlap
        return chunks


@lru_cache
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()
