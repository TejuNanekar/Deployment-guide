"""Read allowlisted files, redact them, and replace their index entries."""

from __future__ import annotations

import re
from pathlib import Path

from app.chunking import chunk_text
from app.config import Settings
from app.manifest import load_documents
from app.models import Chunk, DocumentSpec
from app.observability import log_event
from app.redact import redact
from app.store import VectorStore


def _title(text: str, path: Path) -> str:
    if path.suffix.lower() in {".yml", ".yaml"}:
        match = re.search(r"(?m)^name:\s*[\"']?(.+?)[\"']?\s*$", text)
        if match:
            return match.group(1).strip()
    match = re.search(r"(?m)^#\s+(.+)$", text)
    if match:
        return match.group(1).strip()
    return path.name


def ingest(settings: Settings, store: VectorStore) -> dict[str, object]:
    documents = load_documents(settings)
    indexed: list[DocumentSpec] = []
    missing: list[str] = []
    chunk_count = 0
    seen = {(document.repo_id, document.source_path) for document in documents}
    store.begin_ingest()
    success = False
    try:
        for document in documents:
            path = Path(document.absolute_path)
            if not path.is_file():
                missing.append(f"{document.repo_id}:{document.source_path}")
                if not store.rebuilding:
                    store.delete_document(document.repo_id, document.source_path)
                continue
            text = redact(path.read_text(encoding="utf-8", errors="replace"), path)
            pieces = chunk_text(text, suffix=path.suffix.lower())
            title = _title(text, path)
            chunks = [
                Chunk(chunk_index=index, heading=heading, text=piece, title=title, document=document)
                for index, (heading, piece) in enumerate(pieces)
                if piece.strip()
            ]
            store.replace_document(chunks)
            indexed.append(document)
            chunk_count += len(chunks)

        if not store.rebuilding:
            for existing in store.list_files():
                key = (existing["repo_id"], existing["source_path"])
                if key not in seen:
                    store.delete_document(existing["repo_id"], existing["source_path"])
        success = True
    finally:
        store.finish_ingest(success=success, chunks=chunk_count)

    git_refs = {document.repo_id: document.git_ref for document in indexed}
    unassigned = sum(1 for document in indexed if document.status == "unassigned")
    log_event(
        "ingest",
        project_id=settings.project_id,
        files=len(indexed),
        chunks=chunk_count,
        unassigned=unassigned,
        missing=len(missing),
        embedding_id=store.embedder.identity,
        index=store.index_status,
    )
    return {
        "files": len(indexed),
        "chunks": chunk_count,
        "unassigned": unassigned,
        "git_refs": git_refs,
        "missing": missing,
    }


def main() -> None:
    from app.embeddings import build_embedder

    settings = Settings.from_env()
    store = VectorStore(settings, build_embedder(settings))
    result = ingest(settings, store)
    print(
        f"Indexed {result['files']} files, {result['chunks']} chunks, "
        f"{result['unassigned']} unassigned."
    )
    if result["missing"]:
        print("Missing files:")
        for name in result["missing"]:
            print(f"  {name}")


if __name__ == "__main__":
    main()
