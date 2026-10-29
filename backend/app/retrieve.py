"""Choose which Matrimony components a question is allowed to search."""

from __future__ import annotations

import re

from app.config import Settings

COMPONENTS: dict[str, str] = {
    "api": "Spring Boot API",
    "ui": "React UI",
    "legacy-admin": "Legacy admin",
    "legacy-api": "Legacy PHP API",
    "legacy-portal": "Legacy portal",
    "shared": "Shared server setup",
}

GUIDE_SOURCE = "Matrimony-Deployment-Guide.md"

HOWTO_GROUPS: dict[str, list[str]] = {
    "api": ["api", "platform", "guide"],
    "ui": ["ui", "platform", "guide"],
    "legacy-admin": ["legacy-admin", "legacy", "guide"],
    "legacy-api": ["legacy-api", "legacy", "guide"],
    "legacy-portal": ["legacy-portal", "legacy", "guide"],
    "shared": ["shared", "guide"],
}

WHERE_GROUPS: dict[str, list[str]] = {
    "api": ["api", "platform", "shared", "guide"],
    "ui": ["ui", "platform", "shared", "guide"],
    "legacy-admin": ["legacy-admin", "legacy", "shared", "guide"],
    "legacy-api": ["legacy-api", "legacy", "shared", "guide"],
    "legacy-portal": ["legacy-portal", "legacy", "shared", "guide"],
    "shared": ["shared", "platform", "guide"],
}

ANSWERABLE_STATUS = ["current", "proposed"]
HOWTO_RE = re.compile(r"\b(how do i|how to|deploy|which commands|what commands|steps to)\b", re.I)
WHERE_RE = re.compile(r"\b(where|which directory|what path|repository root)\b", re.I)


def detect_component(question: str) -> str | None:
    text = question.lower()
    checks = [
        ("legacy-admin", r"\blegacy admin\b|\banupam-admin\b|\badmin app\b|\bthe admin\b|\bdeploy the admin\b"),
        ("legacy-portal", r"\bportal\b|\banupam-portal\b|\banupamshaadi-new-app\b"),
        ("legacy-api", r"\blegacy api\b|\banupam-api\b|\banupam_api\b|\bphp api\b"),
        ("ui", r"\breact\b|\bfrontend\b|\bstorefront\b|\bmatrimony ui\b|\bdeploy ui\b|\bthe ui\b"),
        ("api", r"\bspring\b|\bmatrimony-api\b|\bdeploy api\b|\bbackend api\b|\bthe api\b"),
        ("shared", r"\bnginx\b|\bpodman\b|\bserver setup\b|\bfirewall\b|\bvalkey\b|\bbackup\b"),
    ]
    for component, pattern in checks:
        if re.search(pattern, text):
            return component
    return None


def is_howto(question: str) -> bool:
    return HOWTO_RE.search(question) is not None and WHERE_RE.search(question) is None


def is_where(question: str) -> bool:
    return WHERE_RE.search(question) is not None


def component_filter(question: str, component: str | None) -> list[str] | None:
    """Return component labels to search, or None when the app must be chosen first."""
    selected = component or detect_component(question)
    if selected is None and not is_where(question):
        return None
    if selected is None:
        labels: list[str] = []
        for group in WHERE_GROUPS.values():
            for label in group:
                if label not in labels:
                    labels.append(label)
        return labels
    groups = WHERE_GROUPS if is_where(question) else HOWTO_GROUPS
    return groups[selected]


def is_guide_source(source_path: str) -> bool:
    return source_path.replace("\\", "/").endswith(GUIDE_SOURCE)


def script_names_for(labels: list[str], settings: Settings) -> str:
    from pathlib import Path

    from app.manifest import load_documents

    names: list[str] = []
    for document in load_documents(settings):
        if document.component in labels and document.document_type == "script":
            names.append(Path(document.source_path).name)
    return " ".join(dict.fromkeys(names))
