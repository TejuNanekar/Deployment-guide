"""Remove secret values before text is indexed."""

from __future__ import annotations

import re
from pathlib import Path

PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
ASSIGNMENT_RE = re.compile(
    r"(?i)\b((?:[A-Z0-9_]*_)?(?:PASSWORD|SECRET|API_KEY|ACCESS_KEY|SECRET_KEY|TOKEN))(\s*[:=]\s*)(\S+)"
)
CREDENTIAL_URL_RE = re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^/\s:@]+):([^/\s@]+)@")
SECRET_TOKEN_RE = re.compile(r"\b(?:gsk|sk|ghp|github_pat|xox[baprs]|AKIA)[A-Za-z0-9_\-]{8,}\b")
BEARER_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{12,}")
ENV_EXAMPLE_SUFFIXES = {".example", ".env.example"}
SKIP_DIR_NAMES = {"examples", "node_modules", "vendor", "target", "dist", ".git"}


def should_skip(path: Path) -> bool:
    if any(part in SKIP_DIR_NAMES for part in path.parts):
        return True
    name = path.name
    if name == ".env" or name.endswith(".pem") or name.startswith("id_rsa"):
        return True
    if name.endswith(".env") and not name.endswith(".example"):
        return True
    return False


def redact(text: str, path: Path) -> str:
    cleaned = PRIVATE_KEY_RE.sub("<redacted-private-key>", text)
    cleaned = CREDENTIAL_URL_RE.sub(r"\1:<redacted>@", cleaned)
    cleaned = SECRET_TOKEN_RE.sub("<redacted>", cleaned)
    cleaned = BEARER_RE.sub(r"\1<redacted>", cleaned)
    if path.name.endswith(".example") or ".env" in path.name:
        return _redact_env_file(cleaned)
    return ASSIGNMENT_RE.sub(lambda match: _redact_assignment(match), cleaned)


def redact_preview(text: str, limit: int = 180) -> str:
    """Short log-safe copy of a question. Not used for indexed documents."""
    cleaned = redact(text, Path("preview.txt")).replace("\n", " ")
    return cleaned[:limit]


def _redact_env_file(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            lines.append(line)
            continue
        key, _, _value = line.partition("=")
        lines.append(f"{key}=<redacted>")
    return "\n".join(lines)


def _redact_assignment(match: re.Match[str]) -> str:
    value = match.group(3)
    if value.startswith("$") or value.startswith("<") or "secrets." in value:
        return match.group(0)
    return f"{match.group(1)}{match.group(2)}<redacted>"
