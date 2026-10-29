"""Embedding identity and content hashes for the deployment index.

Hash vectors and BAAI/bge-small-en-v1.5 are both 384-dimensional. Dimension
alone cannot tell them apart, so every chunk records the embedder that
produced it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.config import Settings
from app.embeddings import Embedder


def embedding_identity(embedder: Embedder, settings: Settings) -> str:
    if not embedder.semantic:
        return f"hash:token-hash:{embedder.dimensions}"
    return f"{settings.embedding_provider}:{settings.embedding_model}:{embedder.dimensions}"


def model_label(embedder: Embedder, settings: Settings) -> str:
    if not embedder.semantic:
        return "token-hash"
    return settings.embedding_model


def content_hash(text: str, git_ref: str, identity: str) -> str:
    payload = f"{identity}\n{git_ref}\n{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def vector_is_dense(vector: list[float]) -> bool:
    """True when the vector is not a sparse hash embedding.

    Hash embeddings leave most buckets at exactly 0. The sampled bge-small
    vectors in this project had no exact zeros.
    """
    if not vector:
        return False
    zeros = sum(1 for value in vector if value == 0.0)
    return zeros / len(vector) < 0.5


def pointer_path(settings: Settings) -> Path | None:
    if settings.qdrant_path == ":memory:":
        return None
    root = Path(settings.qdrant_path)
    return root.with_name(root.name + ".active.json")


def read_pointer(settings: Settings) -> str | None:
    path = pointer_path(settings)
    if path is None or not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("collection") or "").strip()
    return name or None


def write_pointer(settings: Settings, collection: str, identity: str) -> None:
    path = pointer_path(settings)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps({"collection": collection, "embedding_id": identity}, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)
