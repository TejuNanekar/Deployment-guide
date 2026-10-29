"""Embeddings. FastEmbed is the runtime default. Hashing is for tests only.

Hash vectors are not semantic. They share the 384-dimension size of
BAAI/bge-small-en-v1.5, so callers must compare embedding identity, not size.
"""

from __future__ import annotations

import hashlib
import math
import re

from app.config import Settings

TOKEN_RE = re.compile(r"[a-z0-9_./:-]+", re.IGNORECASE)
HASH_DIMENSIONS = 384


class Embedder:
    dimensions: int
    semantic: bool

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]

    @property
    def identity(self) -> str:
        return f"unknown:unknown:{self.dimensions}"


class HashEmbedder(Embedder):
    """Deterministic bag-of-tokens vectors for tests.

    These vectors are not semantic. Retrieval uses keyword ranking when this
    embedder is active. Do not point a semantic index at this embedder.
    """

    dimensions = HASH_DIMENSIONS
    semantic = False

    @property
    def identity(self) -> str:
        return f"hash:token-hash:{self.dimensions}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_hash_vector(text) for text in texts]


class FastEmbedEmbedder(Embedder):
    """BAAI/bge-small-en-v1.5 passages, with the model's query prefix on searches."""

    semantic = True

    def __init__(self, model_name: str) -> None:
        import os
        from pathlib import Path

        from fastembed import TextEmbedding

        self.model_name = model_name
        cache = Path(__file__).resolve().parents[1] / "data" / "fastembed"
        cache.mkdir(parents=True, exist_ok=True)
        os.environ["HF_HOME"] = str(cache)
        os.environ["HF_HUB_CACHE"] = str(cache / "hub")
        os.environ["TMP"] = str(cache / "tmp")
        os.environ["TEMP"] = str(cache / "tmp")
        (cache / "tmp").mkdir(parents=True, exist_ok=True)
        self._model = TextEmbedding(model_name=model_name, cache_dir=str(cache))
        sample = list(self._model.embed(["dimension probe"]))[0]
        self.dimensions = len(sample)

    @property
    def identity(self) -> str:
        return f"fastembed:{self.model_name}:{self.dimensions}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [list(map(float, vector)) for vector in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        query_embed = getattr(self._model, "query_embed", None)
        if query_embed is not None:
            vector = list(query_embed([text]))[0]
            return list(map(float, vector))
        prefixed = "Represent this sentence for searching relevant passages: " + text
        return self.embed([prefixed])[0]


def build_embedder(settings: Settings) -> Embedder:
    if settings.embedding_provider == "fastembed":
        return FastEmbedEmbedder(settings.embedding_model)
    if settings.embedding_provider != "hash":
        raise ValueError(f"Unknown EMBEDDING_PROVIDER: {settings.embedding_provider}")
    return HashEmbedder()


def _hash_vector(text: str) -> list[float]:
    vector = [0.0] * HASH_DIMENSIONS
    tokens = TOKEN_RE.findall(text.lower())
    if not tokens:
        return vector
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % HASH_DIMENSIONS
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]
