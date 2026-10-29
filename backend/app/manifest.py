"""Load the Matrimony manifest and discover new workflow files."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from app.config import Settings
from app.models import DocumentSpec
from app.redact import should_skip

ANSWERABLE_STATUS = {"current", "proposed"}


def load_documents(settings: Settings) -> list[DocumentSpec]:
    manifest_path = settings.manifest_path
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    roots = {
        "matrimony-platform": settings.matrimony_platform_root,
        "matrimony-platform-ui": settings.matrimony_ui_root,
        "deployment-guide": settings.guide_root or (settings.manifest_path.parent / "guides"),
    }
    declared: dict[tuple[str, str], DocumentSpec] = {}
    git_refs = {repo_id: _git_ref(path) for repo_id, path in roots.items()}
    project_id = str(raw.get("project_id") or settings.project_id or "matrimony-platform")

    for item in raw.get("documents", []):
        repo_id = item["repo"]
        source_path = item["path"].replace("\\", "/")
        absolute = roots[repo_id] / source_path
        if should_skip(absolute):
            continue
        declared[(repo_id, source_path)] = DocumentSpec(
            repo_id=repo_id,
            source_path=source_path,
            absolute_path=str(absolute),
            document_type=item["document_type"],
            component=item["component"],
            environment=item.get("environment", "uat"),
            status=item["status"],
            git_ref=git_refs[repo_id],
            project_id=project_id,
        )

    for watch in raw.get("watch", []):
        repo_id = watch["repo"]
        root = roots[repo_id]
        for pattern in _expand_braces(watch["glob"]):
            for absolute in sorted(root.glob(pattern)):
                if not absolute.is_file() or should_skip(absolute):
                    continue
                _add_watched(declared, watch, repo_id, root, absolute, git_refs[repo_id], project_id)
    return list(declared.values())


def _add_watched(declared, watch, repo_id, root, absolute, git_ref, project_id: str) -> None:
    source_path = absolute.relative_to(root).as_posix()
    key = (repo_id, source_path)
    if key in declared:
        return
    declared[key] = DocumentSpec(
        repo_id=repo_id,
        source_path=source_path,
        absolute_path=str(absolute),
        document_type=watch.get("document_type", "pipeline"),
        component=watch.get("component", "unassigned"),
        environment=watch.get("environment", "uat"),
        status=watch.get("status", "unassigned"),
        git_ref=git_ref,
        project_id=project_id,
    )


def _expand_braces(pattern: str) -> list[str]:
    if "{" not in pattern:
        return [pattern]
    prefix, rest = pattern.split("{", 1)
    group, suffix = rest.split("}", 1)
    return [f"{prefix}{part}{suffix}" for part in group.split(",")]


def _git_ref(root: Path) -> str:
    if not (root / ".git").exists():
        return "unversioned"
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "unversioned"
    return result.stdout.strip() or "unversioned"
