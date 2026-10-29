"""Conversation turns: ask only what is missing, then answer follow-ups in the same chat."""

from __future__ import annotations

import re

from app.config import Settings
from app.models import ChatChoice, ChatRequest, ChatResponse
from app.query import run_query
from app.retrieve import COMPONENTS, detect_component, is_howto, is_where
from app.store import VectorStore

ENVIRONMENTS: list[ChatChoice] = [
    ChatChoice(id="uat", label="UAT"),
    ChatChoice(id="production", label="Production"),
]

APPLICATIONS: list[ChatChoice] = [
    ChatChoice(id=key, label=label) for key, label in COMPONENTS.items() if key != "shared"
]
APPLICATIONS.append(ChatChoice(id="shared", label="Shared server setup"))

TOPIC_RE = re.compile(
    r"\b(deploy|deployment|deploying|process|procedure|rollback|restart|verify|health|logs?|"
    r"nginx|podman|commands?|server|uat|production|admin|portal|api|ui|frontend|backend|"
    r"repository|path|directory|backup|troubleshoot|failed|failure|error|env|release|ship)\b",
    re.IGNORECASE,
)

FOLLOW_RE = re.compile(
    r"\b(log|logs|verify|verification|check|checking|rollback|roll back|sql|schema|downtime|"
    r"next|fail|failed|failure|health|where|after|optional|skip|status|running|container|"
    r"image|workflow|github|branch|why|what if|how long|same app|this app)\b",
    re.IGNORECASE,
)

ENVIRONMENT_ALIASES = {
    "uat": "uat",
    "production": "production",
    "prod": "production",
    "live": "production",
}

APPLICATION_ALIASES = {
    "api": "api",
    "spring": "api",
    "spring boot": "api",
    "spring boot api": "api",
    "backend": "api",
    "backend api": "api",
    "the backend": "api",
    "the api": "api",
    "java api": "api",
    "ui": "ui",
    "react": "ui",
    "react ui": "ui",
    "frontend": "ui",
    "the frontend": "ui",
    "the ui": "ui",
    "admin": "legacy-admin",
    "the admin": "legacy-admin",
    "legacy admin": "legacy-admin",
    "legacy-admin": "legacy-admin",
    "admin panel": "legacy-admin",
    "legacy api": "legacy-api",
    "legacy php api": "legacy-api",
    "legacy-api": "legacy-api",
    "php api": "legacy-api",
    "portal": "legacy-portal",
    "legacy portal": "legacy-portal",
    "legacy-portal": "legacy-portal",
    "shared": "shared",
    "shared server setup": "shared",
    "server setup": "shared",
}
for _key, _label in COMPONENTS.items():
    APPLICATION_ALIASES.setdefault(_label.lower(), _key)


def converse(settings: Settings, store: VectorStore, body: ChatRequest) -> ChatResponse:
    message = body.message.strip()
    named_env = _find_environment(message)
    named_app = _find_application(message)
    selection = _is_selection(message)
    follow_up = bool(body.environment and body.component) and _is_follow_up(message)
    new_question = _looks_like_question(message) and not selection

    if selection:
        question = body.question or message
        environment = named_env or body.environment
        component = named_app or body.component
    elif follow_up:
        question = message
        environment = named_env or body.environment
        component = named_app or body.component
    elif new_question:
        question = message
        environment = named_env or body.environment
        if named_app:
            component = named_app
        elif _is_fresh_howto(message):
            component = None
        else:
            component = body.component
    else:
        question = body.question or message
        environment = named_env or body.environment
        component = named_app or body.component

    if not question:
        return _nudge()
    if not _understands(question) and not (environment and component and follow_up):
        return _nudge()

    if environment is None:
        return _ask_environment(question, component)
    if component is None:
        if body.component and not named_app and new_question:
            return _confirm_application(question, environment, body.component)
        return _ask_application(question, environment)
    return _answer(settings, store, question, environment, component)


def _answer(settings: Settings, store: VectorStore, question: str, environment: str, component: str) -> ChatResponse:
    result = run_query(settings, store, question, environment, component)
    return ChatResponse(
        reply=result.message,
        question=question,
        environment=environment,
        component=component,
        answer=result,
    )


def _nudge() -> ChatResponse:
    return ChatResponse(
        reply=(
            "I can help with Matrimony deploys: the steps, where to run a command, "
            "or how to check that it worked. What do you want to do?"
        )
    )


def _ask_environment(question: str, component: str | None = None, reply: str | None = None) -> ChatResponse:
    if reply is None:
        if component:
            reply = (
                f"You asked about the {_label(component)}. "
                "Which environment is this for — UAT or Production?"
            )
        else:
            reply = "I can walk you through that. Which environment is this for — UAT or Production?"
    return ChatResponse(
        reply=reply,
        choices=ENVIRONMENTS,
        choice_kind="environment",
        question=question,
        component=component,
    )


def _ask_application(question: str, environment: str, reply: str | None = None) -> ChatResponse:
    if reply is None:
        reply = (
            f"On the {_env_label(environment)} server, which application is this for? "
            "Name it in your own words, or pick one."
        )
    return ChatResponse(
        reply=reply,
        choices=APPLICATIONS,
        choice_kind="application",
        question=question,
        environment=environment,
    )


def _confirm_application(question: str, environment: str, component: str) -> ChatResponse:
    return ChatResponse(
        reply=(
            f"Is this still the {_label(component)} on {_env_label(environment)}, "
            "or a different application?"
        ),
        choices=[ChatChoice(id=component, label=_label(component)), *[item for item in APPLICATIONS if item.id != component]],
        choice_kind="application",
        question=question,
        environment=environment,
    )


def _find_environment(message: str) -> str | None:
    text = _normalise(message)
    if text in ENVIRONMENT_ALIASES:
        return ENVIRONMENT_ALIASES[text]
    match = re.search(r"\b(uat|production|prod|live)\b", text)
    if match:
        return ENVIRONMENT_ALIASES[match.group(1)]
    return None


def _find_application(message: str) -> str | None:
    text = _normalise(message)
    if text in APPLICATION_ALIASES:
        return APPLICATION_ALIASES[text]
    for alias, component in sorted(APPLICATION_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return component
    return detect_component(message)


def _is_selection(message: str) -> bool:
    text = _normalise(message)
    if text in ENVIRONMENT_ALIASES or text in APPLICATION_ALIASES:
        return True
    if len(text.split()) > 8:
        return False
    if is_howto(message) or is_where(message) or "?" in message:
        return False
    return _find_environment(message) is not None or _find_application(message) is not None


def _looks_like_question(message: str) -> bool:
    if "?" in message:
        return True
    return is_howto(message) or is_where(message) or (_understands(message) and len(message.split()) >= 4)


def _is_fresh_howto(message: str) -> bool:
    return is_howto(message) and not _is_follow_up(message)


def _is_follow_up(message: str) -> bool:
    if FOLLOW_RE.search(message):
        return True
    if is_where(message):
        return True
    return False


def _understands(message: str) -> bool:
    if len(message.strip()) < 3:
        return False
    return TOPIC_RE.search(message) is not None or is_howto(message) or is_where(message) or FOLLOW_RE.search(message) is not None


def _label(component: str) -> str:
    return COMPONENTS.get(component, component)


def _env_label(environment: str) -> str:
    return "UAT" if environment == "uat" else "Production"


def _normalise(message: str) -> str:
    return re.sub(r"\s+", " ", message.strip().lower())
