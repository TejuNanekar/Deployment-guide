"""Ordered answers copied from the Matrimony Deployment Guide.

The chat model does not write these steps. A deploy question returns every
step for that application, in the guide's order.
"""

from __future__ import annotations

import re

from app.models import AskResponse, CitationModel, StepModel
from app.retrieve import is_guide_source

_HEADING_RE = re.compile(
    r"^\[(?P<kind>deploy|operations|settings|locations)\|(?P<scopes>[a-z0-9,-]+)(?:\|(?P<role>note|step))?\]\s*(?P<title>.*)$"
)
_FENCE_RE = re.compile(r"```([^\n]*)\n(.*?)```", re.DOTALL)
_COMMAND_RE = re.compile(
    r"(?m)^\s*(?:sudo |cd |scp |ssh |curl |dnf |tar |bash |sh |podman |npm |mvn |systemctl |journalctl |"
    r"ln |chmod |chown |install |for |if |php |composer |nginx |echo |useradd |firewall-cmd |git |cp |mv |"
    r"mkdir |openssl |podman-compose |deploy-app |deploy/|df |ls )"
)
_TOPIC_RE = (
    ("rollback", ("rollback", "roll back")),
    ("roll back", ("rollback", "roll back")),
    ("log", ("log",)),
    ("restart", ("restart",)),
    ("backup", ("backup",)),
    ("mysql", ("mysql",)),
    ("disk", ("disk",)),
    ("memory", ("memory",)),
    ("nginx", ("nginx",)),
    ("php", ("php",)),
    ("container", ("container", "podman ps")),
)


def guide_response(question: str, payloads: list[dict], component: str | None) -> AskResponse | None:
    """Return the full guide procedure, or None when this question is not in the guide."""
    if not component:
        return None
    chunks = [payload for payload in payloads if is_guide_source(str(payload.get("source_path", "")))]
    if not chunks:
        return None
    kind = guide_kind(question)
    chunks.sort(key=lambda payload: int(payload.get("chunk_index") or 0))
    notes: list[str] = []
    steps: list[StepModel] = []
    citations: list[CitationModel] = []
    for payload in chunks:
        parsed = _parse_heading(str(payload.get("heading", "")))
        if parsed is None or parsed["kind"] != kind or component not in parsed["scopes"]:
            continue
        if kind == "operations" and not _operations_match(question, parsed["title"], str(payload.get("text", ""))):
            continue
        if parsed["role"] == "note":
            note = _body(payload)
            if note:
                notes.append(note)
                citations.append(_citation(payload))
            continue
        step = _step(payload, parsed["title"])
        if step is None:
            continue
        steps.append(step)
        citations.append(_citation(payload))
    if not steps:
        return None
    return AskResponse(
        answer_kind="steps",
        message=_message(kind, len(steps)),
        steps=steps,
        notes=notes,
        citations=citations,
    )


def guide_kind(question: str) -> str:
    text = question.lower()
    if re.search(r"\b(rollback|roll back)\b", text):
        return "operations"
    if re.search(r"\b(deploy|deployment)\b", text):
        return "deploy"
    if re.search(r"\b(password|passwords|setting|settings|app\.env|secret)\b", text):
        return "settings"
    if re.search(r"\b(where|directory|folder|location|path)\b", text):
        return "locations"
    if re.search(r"\b(logs?|restart|backup|disk|memory|nginx|mysql|container)\b", text):
        return "operations"
    return "deploy"


def _message(kind: str, count: int) -> str:
    if kind == "deploy":
        return (
            f"There are {count} steps. Follow every one, in this order. "
            "Do not stop after the first step. "
            'A step whose heading says "only if" applies only when that condition is true. '
            "This is the full UAT procedure copied from the Matrimony Deployment Guide."
        )
    if kind == "locations":
        return "These locations are copied from the Matrimony Deployment Guide."
    if kind == "settings":
        return "These setting changes are copied from the Matrimony Deployment Guide. No extra commands are added."
    return "These server commands are copied from the Matrimony Deployment Guide. Run them as root after you log in."


def _parse_heading(heading: str) -> dict[str, object] | None:
    match = _HEADING_RE.match(heading.strip())
    if not match:
        return None
    return {
        "kind": match.group("kind"),
        "scopes": match.group("scopes").split(","),
        "role": match.group("role") or "step",
        "title": match.group("title").strip(),
    }


def _operations_match(question: str, title: str, body: str) -> bool:
    text = f"{title}\n{body}".lower()
    question_l = question.lower()
    wanted: list[str] = []
    for key, terms in _TOPIC_RE:
        if key in question_l:
            wanted.extend(terms)
    if not wanted:
        return True
    return any(term in text for term in wanted)


def _step(payload: dict, title: str) -> StepModel | None:
    text = str(payload.get("text", ""))
    fence = _FENCE_RE.search(text)
    if fence:
        command = fence.group(2).strip()
        if not command or not _COMMAND_RE.search(command):
            return None
        before = text[: fence.start()]
        after = text[fence.end() :]
        return _model(
            payload,
            title=title,
            where=_where(title),
            command=command,
            purpose=_purpose(before, title),
            expected=_expected(after),
        )
    body = _body(payload)
    if len(body) < 40:
        return None
    where = (
        "In the browser, on GitHub. Do not paste this into a shell."
        if "github" in title.lower()
        else "This section is a checklist, not a single shell command."
    )
    return _model(payload, title=title, where=where, command=body[:1200], purpose=title, expected=_expected(""))


def _model(payload: dict, *, title: str, where: str, command: str, purpose: str, expected: str) -> StepModel:
    return StepModel(
        where=where,
        command=command,
        purpose=purpose,
        expected=expected,
        source_path=payload.get("source_path", ""),
        git_ref=payload.get("git_ref", ""),
        status=payload.get("status", ""),
        heading=title,
    )


def _where(title: str) -> str:
    lowered = title.lower()
    if "github" in lowered:
        return "In the browser, on GitHub. Do not paste this into a shell."
    if "git bash" in lowered:
        return "Your Windows machine, in Git Bash, at the matrimony-platform repository root"
    if "powershell" in lowered or "local" in lowered:
        return "Your Windows machine, in PowerShell"
    if "server" in lowered:
        return "On the server, in an SSH session as root"
    return "The source does not say where to run this. Do not guess a machine."


def _purpose(before: str, title: str) -> str:
    lines = [
        line.strip()
        for line in before.splitlines()
        if line.strip() and not line.strip().startswith("```") and not line.strip().startswith("#")
    ]
    if lines and (_HEADING_RE.match(lines[0]) or lines[0] == title):
        lines = lines[1:]
    if not lines:
        return title
    return " ".join(lines)[:500]


def _expected(after: str) -> str:
    lines = [line.strip() for line in after.splitlines() if line.strip() and not line.strip().startswith("```")]
    if not lines:
        return "The source does not state an expected result next to this command."
    return " ".join(lines)[:500]


def _body(payload: dict) -> str:
    heading = str(payload.get("heading", "")).strip()
    lines = []
    for line in str(payload.get("text", "")).splitlines():
        stripped = line.strip()
        if not stripped or stripped == heading or stripped.startswith("```"):
            continue
        lines.append(stripped)
    return "\n".join(lines).strip()


def _citation(payload: dict) -> CitationModel:
    return CitationModel(
        source_path=payload.get("source_path", ""),
        heading=str(payload.get("heading", "")),
        git_ref=payload.get("git_ref", ""),
        status=payload.get("status", ""),
        component=payload.get("component", ""),
        excerpt=str(payload.get("text", "")).strip()[:700],
    )
