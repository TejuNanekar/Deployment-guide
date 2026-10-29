"""Ask the language model to write the answer from retrieved passages.

Retrieved text is context for the model. It is not returned as the answer.
If the model does not answer, the passages are not shown in its place.
"""

from __future__ import annotations

from app.config import Settings
from app.llm import LlmService
from app.models import AskResponse, CitationModel, ComponentOption
from app.retrieve import COMPONENTS

_SYSTEM = (
    "You answer questions about the Matrimony UAT deployment. "
    "The user message contains passages retrieved from indexed files. "
    "Write the answer yourself. Use only facts and commands that appear in those passages. "
    "Do not invent a hostname, path, service name, branch, or command. "
    "If the passages do not contain the answer, say it is not documented. "
    "Do not tell the user to read a guide instead of answering.\n"
    "Format a procedure so it can be followed on screen:\n"
    "1. A first-level heading (`#`) that names the application and environment.\n"
    "2. One sentence under it: what changes, and where it runs.\n"
    "3. One section per step. Use a second-level heading: ## 1. Step name\n"
    "4. Inside each step, in this order, and only when the passages support the line:\n"
    "   - **Why:** one sentence on why this step is done. Omit it if the passages give no reason.\n"
    "   - **Where:** laptop, GitHub, or the server.\n"
    "   - The exact commands in one fenced code block. Name the shell when the passages show one.\n"
    "   - **Done when:** the result the passages mention.\n"
    "5. If a step is optional, put (optional) in the heading and say when to skip it on the Why line.\n"
    "6. End with ## Keep in mind and a short bullet list of facts that are not commands, such as downtime, branch, or rollback. Do not repeat the steps.\n"
    "7. Bold only the labels Why, Where, and Done when, plus a name the reader must not mix up, such as a branch or hostname.\n"
    "8. Do not wrap the whole answer in a code block. Do not add a sources list."
)


def answer_question(
    question: str,
    payloads: list[dict],
    *,
    component: str | None,
    settings: Settings,
) -> AskResponse:
    if not payloads:
        return AskResponse(
            answer_kind="not_documented",
            message="No matching passage was retrieved, so the language model was not asked.",
        )
    citations = _citations(payloads)
    notes = _notes(payloads)
    if not settings.llm_enabled:
        return AskResponse(
            answer_kind="model_unavailable",
            message="The language model is not configured, so there is no answer. Retrieved document text is not shown in its place.",
            notes=notes,
            citations=citations,
        )
    content = LlmService(settings).complete(_SYSTEM, _user_prompt(question, component, payloads))
    if not content:
        return AskResponse(
            answer_kind="model_unavailable",
            message="The language model did not return an answer. Retrieved document text is not shown in its place.",
            notes=notes,
            citations=citations,
        )
    notes.append("This answer was written by the language model from the retrieved files.")
    return AskResponse(
        answer_kind="model",
        message=content,
        notes=notes,
        citations=citations,
    )


def _user_prompt(question: str, component: str | None, payloads: list[dict]) -> str:
    blocks: list[str] = []
    used = 0
    for payload in payloads:
        text = str(payload.get("text", "")).strip()
        if not text:
            continue
        block = (
            f"Source: {payload.get('source_path', '')}\n"
            f"Heading: {payload.get('heading', '')}\n"
            f"{text}"
        )
        if used + len(block) > 12000:
            break
        blocks.append(block)
        used += len(block)
    application = component or "not specified"
    passages = "\n\n".join(blocks)
    return f"Question: {question}\nApplication: {application}\n\nPassages:\n{passages}"


def clarify_response() -> AskResponse:
    return AskResponse(
        answer_kind="clarify",
        message="Name which application on the Matrimony server you want to deploy. These applications do not share a procedure.",
        components=[ComponentOption(id=key, label=label) for key, label in COMPONENTS.items() if key != "shared"],
    )


def production_response() -> AskResponse:
    return AskResponse(
        answer_kind="not_documented",
        message=(
            "A production deployment procedure is not indexed. "
            "The Matrimony strategy describes production as later gates, and the legacy guide says the .com names stay on the old server. "
            "UAT commands are not repeated here as production steps."
        ),
    )


def _citations(payloads: list[dict]) -> list[CitationModel]:
    citations: list[CitationModel] = []
    for payload in payloads:
        text = payload.get("text", "").strip()
        citations.append(
            CitationModel(
                source_path=payload.get("source_path", ""),
                heading=payload.get("heading", ""),
                git_ref=payload.get("git_ref", ""),
                status=payload.get("status", ""),
                component=payload.get("component", ""),
                excerpt=text[:2000],
            )
        )
    return citations


def _notes(payloads: list[dict]) -> list[str]:
    notes: list[str] = []
    paths = {payload.get("source_path", "") for payload in payloads}
    statuses = {payload.get("status", "") for payload in payloads}
    joined = "\n".join(payload.get("text", "") for payload in payloads)
    if "proposed" in statuses:
        notes.append("One source file is still marked proposed. A hostname in that file is an example, not a confirmed server name.")
    if "uat.example.com" in joined and "anupamshaadi.in" in joined:
        notes.append(
            "DEPLOYMENT_STRATEGY.md uses the example name uat.example.com. "
            "LEGACY_APPS_DEPLOYMENT.md names this UAT server anupamshaadi.in."
        )
    if "outdated" in statuses:
        notes.append("An outdated file was retrieved. Do not treat it as the current procedure.")
    if any(path.endswith("backend.env.example") for path in paths):
        notes.append("Environment values from backend.env.example are redacted. The index stores variable names only.")
    return notes


