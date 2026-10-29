"""HTTP API. The service never opens SSH sessions or runs deploy commands."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.chat import converse
from app.config import Settings
from app.embeddings import build_embedder
from app.ingest import ingest
from app.models import AskRequest, AskResponse, CatalogFile, CatalogResponse, ChatRequest, ChatResponse, IngestResponse
from app.query import run_query
from app.store import VectorStore


def create_app(settings: Settings | None = None) -> FastAPI:
    default_level = "WARNING" if os.environ.get("PYTEST_CURRENT_TEST") else "INFO"
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", default_level), format="%(message)s")
    settings = settings or Settings.from_env()
    embedder = build_embedder(settings)
    store = VectorStore(settings, embedder)
    app = FastAPI(title="Matrimony deployment assistant", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.store = store

    @app.get("/health")
    def health() -> dict[str, str]:
        provider = "groq" if settings.groq_api_key else "off"
        return {
            "status": "blocked" if store.index_block_reason else "ok",
            "embedding": settings.embedding_provider,
            "embedding_model": settings.embedding_model,
            "embedding_id": store.embedder.identity,
            "semantic": "true" if store.embedder.semantic else "false",
            "index": store.index_status,
            "project_id": settings.project_id,
            "llm": provider,
        }

    @app.post("/ingest", response_model=IngestResponse)
    def ingest_route() -> IngestResponse:
        result = ingest(settings, store)
        return IngestResponse(
            files=int(result["files"]),
            chunks=int(result["chunks"]),
            unassigned=int(result["unassigned"]),
            git_refs=dict(result["git_refs"]),
        )

    @app.get("/catalog", response_model=CatalogResponse)
    def catalog() -> CatalogResponse:
        files = [CatalogFile(**item) for item in store.list_files()]
        return CatalogResponse(
            project_id="matrimony-platform",
            files=files,
            unassigned=[item for item in files if item.status == "unassigned"],
        )

    @app.post("/ask", response_model=AskResponse)
    def ask(body: AskRequest) -> AskResponse:
        return run_query(settings, store, body.question, body.environment, body.component, debug=body.debug)

    @app.post("/chat", response_model=ChatResponse)
    def chat(body: ChatRequest) -> ChatResponse:
        return converse(settings, store, body)

    return app


app = FastAPI(title="Matrimony deployment assistant") if os.environ.get("PYTEST_VERSION") else create_app()
