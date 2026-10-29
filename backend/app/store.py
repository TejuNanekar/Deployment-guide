"""Qdrant storage. Local files are the default; a URL targets a Qdrant server."""

from __future__ import annotations

import re
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchAny,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.config import Settings
from app.embeddings import Embedder
from app.index_meta import content_hash, model_label, read_pointer, vector_is_dense, write_pointer
from app.models import Chunk
from app.observability import log_event
from app.retrieve import GUIDE_SOURCE, is_guide_source

POINT_NAMESPACE = uuid.UUID("6f4d8a1e-3c2b-4f5a-9d7e-1b2c3d4e5f60")


class VectorStore:
    def __init__(self, settings: Settings, embedder: Embedder) -> None:
        self.settings = settings
        self.embedder = embedder
        self.client = _client(settings)
        self._read_collection = settings.collection_name
        self._write_collection: str | None = None
        self._rebuilding = False
        self.index_status = "unknown"
        self.index_block_reason = ""
        pointed = read_pointer(settings)
        if pointed:
            self._read_collection = pointed
        self._ensure_collection()
        self._assess_index()

    @property
    def rebuilding(self) -> bool:
        return self._rebuilding

    def _write_name(self) -> str:
        return self._write_collection or self._read_collection

    def begin_ingest(self) -> None:
        """Write in place, or into a staging collection when the live index is blocked."""
        self._write_collection = None
        self._rebuilding = False
        if not self.index_block_reason:
            return
        staging = f"{self.settings.collection_name}__next"
        names = {item.name for item in self.client.get_collections().collections}
        if staging in names:
            self.client.delete_collection(staging)
        self.client.create_collection(
            collection_name=staging,
            vectors_config=VectorParams(size=self.embedder.dimensions, distance=Distance.COSINE),
        )
        self._write_collection = staging
        self._rebuilding = True
        log_event(
            "ingest_staging",
            collection=staging,
            reason=self.index_block_reason,
            embedding_id=self.embedder.identity,
        )

    def finish_ingest(self, *, success: bool, chunks: int) -> None:
        if not self._rebuilding:
            self._assess_index()
            return
        staging = self._write_collection
        self._write_collection = None
        self._rebuilding = False
        if not success or chunks <= 0 or not staging:
            self._drop_collection(staging)
            log_event("ingest_staging_discarded", collection=staging, chunks=chunks, success=success)
            return
        if self._count(staging) <= 0:
            self._drop_collection(staging)
            log_event("ingest_staging_discarded", collection=staging, chunks=0, success=False)
            return
        previous = self._read_collection
        write_pointer(self.settings, staging, self.embedder.identity)
        self._read_collection = staging
        self.index_block_reason = ""
        if previous and previous != staging:
            self._drop_collection(previous)
        self._assess_index()
        log_event(
            "ingest_promoted",
            collection=staging,
            previous=previous,
            embedding_id=self.embedder.identity,
            index=self.index_status,
        )

    def _drop_collection(self, name: str | None) -> None:
        if not name:
            return
        names = {item.name for item in self.client.get_collections().collections}
        if name in names:
            self.client.delete_collection(name)

    def _count(self, name: str) -> int:
        info = self.client.get_collection(name)
        if info.points_count:
            return int(info.points_count)
        return len(_scroll(self.client, name, None))

    def replace_document(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        document = chunks[0].document
        target = self._write_name()
        identity = self.embedder.identity
        hashes = [content_hash(chunk.text, document.git_ref, identity) for chunk in chunks]
        if not self._rebuilding and self._same_document(target, document, hashes, identity):
            return
        vectors = self.embedder.embed([chunk.text for chunk in chunks])
        points = []
        for chunk, vector, digest in zip(chunks, vectors, hashes, strict=True):
            payload = _payload(chunk)
            payload["content_hash"] = digest
            payload["embedding_id"] = identity
            payload["embedding_provider"] = self.settings.embedding_provider
            payload["embedding_model"] = model_label(self.embedder, self.settings)
            points.append(
                PointStruct(
                    id=_point_id(document.repo_id, document.source_path, chunk.chunk_index),
                    vector=vector,
                    payload=payload,
                )
            )
        self.client.upsert(collection_name=target, points=points)
        self._delete_stale(target, document, {point.id for point in points})

    def delete_document(self, repo_id: str, source_path: str) -> None:
        self.client.delete(
            collection_name=self._write_name(),
            points_selector=FilterSelector(filter=_document_filter(repo_id, source_path)),
        )

    def _same_document(self, collection: str, document: Any, hashes: list[str], identity: str) -> bool:
        points = _scroll(self.client, collection, _document_filter(document.repo_id, document.source_path))
        found: dict[int, str] = {}
        for point in points:
            payload = point.payload or {}
            if payload.get("embedding_id") != identity:
                return False
            found[int(payload.get("chunk_index") or 0)] = str(payload.get("content_hash") or "")
        expected = {index: digest for index, digest in enumerate(hashes)}
        return found == expected

    def _delete_stale(self, collection: str, document: Any, keep_ids: set[str]) -> None:
        points = _scroll(self.client, collection, _document_filter(document.repo_id, document.source_path))
        stale = [point.id for point in points if point.id not in keep_ids]
        if stale:
            self.client.delete(collection_name=collection, points_selector=stale)

    def search(
        self,
        question: str,
        *,
        environment: str,
        components: list[str],
        statuses: list[str],
        limit: int,
        prefer_commands: bool = False,
    ) -> list[dict[str, Any]]:
        if self.index_block_reason:
            return []
        query_filter = Filter(
            must=[
                FieldCondition(key="project_id", match=MatchValue(value=self.settings.project_id)),
                FieldCondition(key="environment", match=MatchValue(value=environment)),
                FieldCondition(key="component", match=MatchAny(any=components)),
                FieldCondition(key="status", match=MatchAny(any=statuses)),
            ]
        )
        points = _scroll(self.client, self._read_collection, query_filter)
        if not points:
            return []
        guide_chunks = [
            dict(point.payload or {})
            for point in points
            if is_guide_source(str((point.payload or {}).get("source_path", "")))
        ]
        guide_chunks.sort(key=lambda payload: int(payload.get("chunk_index") or 0))
        other_points = [
            point
            for point in points
            if not is_guide_source(str((point.payload or {}).get("source_path", "")))
        ]
        ranked_ids = _bm25_rank(question, other_points)
        if self.embedder.semantic and other_points:
            dense_ids = self._dense_rank(question, _exclude_guide(query_filter), limit=20)
            ranked_ids = _reciprocal_rank_fusion([ranked_ids, dense_ids])
        by_id = {point.id: point for point in other_points}
        ranked_payloads = [dict(by_id[point_id].payload or {}) for point_id in ranked_ids if point_id in by_id]
        if prefer_commands:
            all_payloads = [dict(point.payload or {}) for point in other_points]
            selected = _commands_from_best_document(ranked_payloads, all_payloads, limit)
        else:
            selected = ranked_payloads[:limit]
        if guide_chunks:
            return guide_chunks + selected
        return selected

    def list_files(self) -> list[dict[str, Any]]:
        points = _scroll(self.client, self._read_collection, None)
        files: dict[tuple[str, str], dict[str, Any]] = {}
        for point in points:
            payload = point.payload or {}
            if payload.get("project_id") != self.settings.project_id:
                continue
            key = (payload.get("repo_id", ""), payload.get("source_path", ""))
            files[key] = {
                "repo_id": payload.get("repo_id", ""),
                "source_path": payload.get("source_path", ""),
                "component": payload.get("component", ""),
                "environment": payload.get("environment", ""),
                "status": payload.get("status", ""),
                "document_type": payload.get("document_type", ""),
                "git_ref": payload.get("git_ref", ""),
            }
        return sorted(files.values(), key=lambda item: (item["repo_id"], item["source_path"]))

    def _dense_rank(self, question: str, query_filter: Filter, limit: int) -> list[str]:
        vector = self.embedder.embed_query(question)
        if hasattr(self.client, "query_points"):
            result = self.client.query_points(
                collection_name=self._read_collection,
                query=vector,
                query_filter=query_filter,
                limit=limit,
            )
            hits = result.points
        else:
            hits = self.client.search(
                collection_name=self._read_collection,
                query_vector=vector,
                query_filter=query_filter,
                limit=limit,
            )
        return [hit.id for hit in hits]

    def _ensure_collection(self) -> None:
        name = self._read_collection
        existing = {item.name for item in self.client.get_collections().collections}
        if name not in existing:
            if name != self.settings.collection_name and self.settings.collection_name in existing:
                self._read_collection = self.settings.collection_name
                name = self._read_collection
            else:
                self.client.create_collection(
                    collection_name=self.settings.collection_name,
                    vectors_config=VectorParams(size=self.embedder.dimensions, distance=Distance.COSINE),
                )
                self._read_collection = self.settings.collection_name
                self.index_status = "empty"
                return
        info = self.client.get_collection(name)
        size = _vector_size(info)
        if size != self.embedder.dimensions:
            self.index_status = "dimension-mismatch"
            self.index_block_reason = (
                f"Index vectors are {size}-dimensional and the active embedder "
                f"{self.embedder.identity} is {self.embedder.dimensions}-dimensional. "
                "Re-index before asking questions. The current index was left in place."
            )

    def _assess_index(self) -> None:
        if self.index_status == "dimension-mismatch":
            return
        try:
            info = self.client.get_collection(self._read_collection)
        except Exception:
            self.index_status = "unknown"
            return
        if not int(info.points_count or 0):
            self.index_status = "empty"
            self.index_block_reason = ""
            return
        points, _offset = self.client.scroll(
            collection_name=self._read_collection,
            limit=1,
            with_payload=True,
            with_vectors=True,
        )
        if not points:
            self.index_status = "empty"
            self.index_block_reason = ""
            return
        payload = points[0].payload or {}
        identity = self.embedder.identity
        stored = str(payload.get("embedding_id") or "")
        if stored:
            if stored != identity:
                self.index_status = "identity-mismatch"
                self.index_block_reason = (
                    f"Index embedding is {stored}. The active embedder is {identity}. "
                    "Re-index before asking questions. The current index was left in place."
                )
            else:
                self.index_status = "ready"
                self.index_block_reason = ""
            return
        vector = _flat_vector(points[0].vector)
        dense = vector_is_dense(vector)
        provider = self.settings.embedding_provider
        if provider == "hash" and dense:
            self.index_status = "unlabeled-dense"
            self.index_block_reason = (
                "This index contains dense vectors and EMBEDDING_PROVIDER=hash is not semantic. "
                "Re-index with the embedder that built the index. The current index was left in place."
            )
            return
        if provider != "hash" and not dense:
            self.index_status = "unlabeled-sparse"
            self.index_block_reason = (
                "This index looks like hash vectors, but a semantic embedder is active. "
                "Re-index before asking questions. The current index was left in place."
            )
            return
        self.index_status = "unlabeled-dense" if dense else "unlabeled-hash"
        self.index_block_reason = ""


def _exclude_guide(query_filter: Filter) -> Filter:
    """Keep the deployment guide out of the ranking so one step cannot crowd out the rest."""
    excluded = list(query_filter.must_not or [])
    excluded.append(FieldCondition(key="source_path", match=MatchValue(value=GUIDE_SOURCE)))
    return Filter(must=query_filter.must, must_not=excluded)


def _client(settings: Settings) -> QdrantClient:
    if settings.qdrant_url:
        return QdrantClient(url=settings.qdrant_url)
    if settings.qdrant_path == ":memory:":
        return QdrantClient(path=":memory:")
    return QdrantClient(path=settings.qdrant_path)


def _payload(chunk: Chunk) -> dict[str, Any]:
    document = chunk.document
    return {
        "text": chunk.text,
        "heading": chunk.heading,
        "chunk_index": chunk.chunk_index,
        "project_id": document.project_id,
        "repo_id": document.repo_id,
        "source_path": document.source_path,
        "document_type": document.document_type,
        "component": document.component,
        "environment": document.environment,
        "status": document.status,
        "git_ref": document.git_ref,
        "title": chunk.title,
    }


def _point_id(repo_id: str, source_path: str, chunk_index: int) -> str:
    return str(uuid.uuid5(POINT_NAMESPACE, f"{repo_id}\n{source_path}\n{chunk_index}"))


def _scroll(client: QdrantClient, collection: str, query_filter: Filter | None) -> list[Any]:
    points: list[Any] = []
    offset = None
    while True:
        batch, offset = client.scroll(
            collection_name=collection,
            scroll_filter=query_filter,
            limit=128,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points.extend(batch)
        if offset is None:
            break
    return points


def _commands_from_best_document(
    ranked_payloads: list[dict],
    all_payloads: list[dict],
    limit: int,
) -> list[dict]:
    """Prefer procedure and pipeline files over scripts when choosing commands."""
    if not ranked_payloads:
        return []
    preferred = [
        payload
        for payload in ranked_payloads
        if payload.get("document_type") in {"deployment", "pipeline"}
    ]
    pool = preferred or ranked_payloads
    keys: list[tuple[str, str]] = []
    for payload in pool:
        key = (str(payload.get("repo_id")), str(payload.get("source_path")))
        if key not in keys:
            keys.append(key)
        if len(keys) == 2:
            break
    selected: list[dict] = []
    for key in keys:
        in_document = [payload for payload in all_payloads if (payload.get("repo_id"), payload.get("source_path")) == key]
        in_document.sort(key=lambda payload: int(payload.get("chunk_index") or 0))
        if not in_document:
            in_document = [payload for payload in pool if (payload.get("repo_id"), payload.get("source_path")) == key]
        if in_document and in_document[0].get("document_type") == "pipeline":
            header = [payload for payload in in_document if payload.get("chunk_index") == 0]
            selected.extend(header[:1] or in_document[:1])
            continue
        procedure = _procedure_payloads(in_document)
        if procedure:
            selected.extend(procedure)
            continue
        ranked_fenced = [
            payload
            for payload in pool
            if (payload.get("repo_id"), payload.get("source_path")) == key and "```" in payload.get("text", "")
        ]
        ranked_fenced.sort(key=lambda payload: int(payload.get("chunk_index") or 0))
        fenced = [payload for payload in in_document if "```" in payload.get("text", "")]
        selected.extend((ranked_fenced or fenced)[:5])
    if any(payload.get("procedure_order") for payload in selected):
        return selected[: max(limit, 12)]
    return selected[:limit]


_SECTION_HEADING = re.compile(r"^(\d+(?:\.\d+)?)(?:\s|\.|$)")
_FENCE = re.compile(r"```([^\n]*)\n(.*?)```", re.DOTALL)
_USER_COMMAND = re.compile(
    r"(?m)^\s*(?:sudo |cd |scp |ssh |curl |dnf |tar |bash |sh |podman |npm |systemctl |ln |chmod |chown |install |for |if |php |composer |nginx |echo |useradd |firewall-cmd |git |cp |mv |mkdir |openssl |podman-compose )",
)
_NON_COMMAND_FENCE = {"text", "php", "yaml", "yml", "json", "md", "markdown"}


def _procedure_payloads(chunks: list[dict]) -> list[dict]:
    """Return one chunk per section in the guide's order table.

    File order is wrong for this guide: section 3.5 is written before section 4,
    and the table says to copy uploads only after deploy-legacy.sh.
    """
    order = _section_order(chunks)
    if not order:
        return []
    selected: list[dict] = []
    for section in order:
        matches = [chunk for chunk in chunks if _heading_section(chunk) == section]
        if not matches:
            continue
        commands = [chunk for chunk in matches if _has_user_command(chunk.get("text", ""))]
        if commands:
            chosen = _with_trailing_notes(commands, matches)
        else:
            chosen = [_joined_chunk(matches)]
        for chunk in chosen:
            marked = dict(chunk)
            marked["procedure_order"] = True
            selected.append(marked)
    return selected


def _section_order(chunks: list[dict]) -> list[str]:
    for chunk in chunks:
        heading = str(chunk.get("heading", ""))
        text = str(chunk.get("text", ""))
        if "order of operations" not in heading.lower() and "order of operations" not in text.lower():
            continue
        found: list[str] = []
        for line in text.splitlines():
            if not line.strip().startswith("|"):
                continue
            cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
            if len(cells) < 3:
                continue
            section = cells[-1].replace("*", "").strip()
            if re.fullmatch(r"\d+(?:\.\d+)?", section) and section not in found:
                found.append(section)
        if found:
            return found
    return []


def _heading_section(chunk: dict) -> str | None:
    match = _SECTION_HEADING.match(str(chunk.get("heading", "")).strip())
    return match.group(1) if match else None


def _has_user_command(text: str) -> bool:
    for match in _FENCE.finditer(text):
        language = match.group(1).strip().lower()
        if language in _NON_COMMAND_FENCE:
            continue
        if _USER_COMMAND.search(match.group(2)):
            return True
    return False


def _with_trailing_notes(commands: list[dict], section_chunks: list[dict]) -> list[dict]:
    """Keep the sentence after a command on that same step."""
    last_index = int(commands[-1].get("chunk_index") or 0)
    notes = [
        _without_heading(chunk)
        for chunk in section_chunks
        if int(chunk.get("chunk_index") or 0) > last_index and "```" not in chunk.get("text", "")
    ]
    notes = [note for note in notes if note]
    if not notes:
        return commands
    merged = dict(commands[-1])
    merged["text"] = "\n\n".join([commands[-1].get("text", ""), *notes]).strip()
    return [*commands[:-1], merged]


def _without_heading(chunk: dict) -> str:
    heading = str(chunk.get("heading", "")).strip()
    lines = [line for line in str(chunk.get("text", "")).splitlines() if line.strip() and line.strip() != heading]
    return "\n".join(lines).strip()


def _joined_chunk(chunks: list[dict]) -> dict:
    if len(chunks) == 1:
        return chunks[0]
    merged = dict(chunks[0])
    merged["text"] = "\n\n".join(chunk.get("text", "") for chunk in chunks).strip()
    return merged


def _bm25_rank(question: str, points: list[Any]) -> list[str]:
    documents = [_tokenize((point.payload or {}).get("text", "")) for point in points]
    scores = _bm25(documents, _tokenize(question))
    order = sorted(range(len(points)), key=lambda index: scores[index], reverse=True)
    return [points[index].id for index in order if scores[index] > 0]


_EXACT_RE = re.compile(r"[a-z0-9_./:-]+", re.IGNORECASE)


def _tokenize(text: str) -> list[str]:
    lowered = text.lower()
    exact = [
        token
        for token in _EXACT_RE.findall(lowered)
        if len(token) > 1 and any(symbol in token for symbol in "._/-:") and token not in STOPWORDS
    ]
    cleaned = lowered.replace("/", " ").replace("\\", " ").replace("_", " ").replace("-", " ").replace(".", " ")
    split = [token for token in cleaned.split() if len(token) > 1 and token not in STOPWORDS]
    return exact + split


STOPWORDS = {
    "a",
    "an",
    "and",
    "do",
    "for",
    "how",
    "i",
    "in",
    "is",
    "my",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "where",
    "which",
}


def _bm25(documents: list[list[str]], query: list[str], k1: float = 1.5, b: float = 0.75) -> list[float]:
    if not documents or not query:
        return [0.0 for _ in documents]
    doc_count = len(documents)
    avg = sum(len(doc) for doc in documents) / doc_count
    df: dict[str, int] = {}
    for doc in documents:
        for term in set(doc):
            df[term] = df.get(term, 0) + 1
    scores: list[float] = []
    for doc in documents:
        tf: dict[str, int] = {}
        for term in doc:
            tf[term] = tf.get(term, 0) + 1
        score = 0.0
        for term in query:
            if term not in tf:
                continue
            idf = math_log((doc_count - df[term] + 0.5) / (df[term] + 0.5) + 1)
            freq = tf[term]
            denom = freq + k1 * (1 - b + b * len(doc) / (avg or 1))
            score += idf * (freq * (k1 + 1)) / denom
        scores.append(score)
    return scores


def math_log(value: float) -> float:
    import math

    return math.log(value)


def _reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> list[str]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, point_id in enumerate(ranking):
            scores[point_id] = scores.get(point_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=lambda point_id: scores[point_id], reverse=True)


def _document_filter(repo_id: str, source_path: str) -> Filter:
    return Filter(
        must=[
            FieldCondition(key="repo_id", match=MatchValue(value=repo_id)),
            FieldCondition(key="source_path", match=MatchValue(value=source_path)),
        ]
    )


def _flat_vector(vector: Any) -> list[float]:
    if vector is None:
        return []
    if isinstance(vector, dict):
        vector = next(iter(vector.values()), [])
    return [float(value) for value in vector]


def _vector_size(info: Any) -> int | None:
    params = info.config.params.vectors
    if hasattr(params, "size"):
        return int(params.size)
    return None
