"""Run one grounded lookup after the environment and application are known."""

from __future__ import annotations

import re
import time

from app.answer import answer_question, clarify_response, production_response
from app.config import Settings
from app.models import AskResponse, TraceModel
from app.observability import log_event
from app.redact import redact_preview
from app.retrieve import ANSWERABLE_STATUS, HOWTO_GROUPS, component_filter, detect_component, is_howto, script_names_for
from app.store import VectorStore

_PRODUCTION_RE = re.compile(r"\b(?:production|prod)\b", re.IGNORECASE)


def asks_for_production(question: str) -> bool:
    return _PRODUCTION_RE.search(question) is not None


def run_query(
    settings: Settings,
    store: VectorStore,
    question: str,
    environment: str,
    component: str | None,
    *,
    debug: bool = False,
) -> AskResponse:
    started = time.perf_counter()
    selected_environment = environment.strip().lower()
    if store.index_block_reason:
        return _finish(
            settings,
            store,
            question=question,
            environment=selected_environment,
            component=component,
            outcome="index_blocked",
            response=AskResponse(answer_kind="not_documented", message=store.index_block_reason),
            started=started,
            sources=[],
            debug=debug,
        )
    if selected_environment == "production" or asks_for_production(question):
        return _finish(
            settings,
            store,
            question=question,
            environment=selected_environment,
            component=component,
            outcome="production_blocked",
            response=production_response(),
            started=started,
            sources=[],
            debug=debug,
        )
    if selected_environment != "uat":
        return _finish(
            settings,
            store,
            question=question,
            environment=selected_environment,
            component=component,
            outcome="environment_rejected",
            response=AskResponse(
                answer_kind="not_documented",
                message="The only indexed environment is UAT. Ask again with environment set to uat.",
            ),
            started=started,
            sources=[],
            debug=debug,
        )
    selected = component or detect_component(question)
    if selected and selected not in HOWTO_GROUPS:
        return _finish(
            settings,
            store,
            question=question,
            environment=selected_environment,
            component=selected,
            outcome="unknown_component",
            response=AskResponse(
                answer_kind="not_documented",
                message="That component is not one of the Matrimony applications in the index.",
            ),
            started=started,
            sources=[],
            debug=debug,
        )
    labels = component_filter(question, selected)
    if labels is None:
        return _finish(
            settings,
            store,
            question=question,
            environment=selected_environment,
            component=selected,
            outcome="clarify",
            response=clarify_response(),
            started=started,
            sources=[],
            debug=debug,
        )
    search_text = question
    prefer_commands = is_howto(question)
    if prefer_commands:
        extra = script_names_for(labels, settings)
        if extra:
            search_text = f"{question} {extra}"
    payloads = store.search(
        search_text,
        environment="uat",
        components=labels,
        statuses=ANSWERABLE_STATUS,
        limit=8,
        prefer_commands=prefer_commands,
    )
    sources = list(dict.fromkeys(str(payload.get("source_path") or "") for payload in payloads if payload.get("source_path")))
    response = answer_question(question, payloads, component=selected, settings=settings)
    outcome = "steps" if response.steps else response.answer_kind
    return _finish(
        settings,
        store,
        question=question,
        environment=selected_environment,
        component=selected,
        outcome=outcome,
        response=response,
        started=started,
        sources=sources,
        debug=debug,
    )


def _finish(
    settings: Settings,
    store: VectorStore,
    *,
    question: str,
    environment: str,
    component: str | None,
    outcome: str,
    response: AskResponse,
    started: float,
    sources: list[str],
    debug: bool,
) -> AskResponse:
    elapsed = int((time.perf_counter() - started) * 1000)
    log_event(
        "query",
        project_id=settings.project_id,
        environment=environment,
        component=component,
        outcome=outcome,
        index=store.index_status,
        embedding_id=store.embedder.identity,
        semantic=store.embedder.semantic,
        sources=sources,
        latency_ms=elapsed,
        question=redact_preview(question),
    )
    if debug:
        response = response.model_copy(
            update={
                "trace": TraceModel(
                    project_id=settings.project_id,
                    environment=environment,
                    component=component,
                    embedding_id=store.embedder.identity,
                    semantic=store.embedder.semantic,
                    index_status=store.index_status,
                    outcome=outcome,
                    sources=sources,
                    latency_ms=elapsed,
                )
            }
        )
    return response
