"""Runtime settings loaded from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


def load_env_file(path: Path) -> None:
    """Load KEY=value lines. Existing process variables stay as they are."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value is None or value.strip() == "" else value


def _project_id(manifest: Path) -> str:
    configured = _env("PROJECT_ID", "")
    if configured:
        return configured
    if not manifest.is_file():
        return "matrimony-platform"
    try:
        raw = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except OSError:
        return "matrimony-platform"
    if isinstance(raw, dict):
        value = str(raw.get("project_id") or "").strip()
        if value:
            return value
    return "matrimony-platform"


@dataclass(frozen=True)
class Settings:
    matrimony_platform_root: Path
    matrimony_ui_root: Path
    manifest_path: Path
    qdrant_path: str
    qdrant_url: str
    collection_name: str
    embedding_provider: str
    embedding_model: str
    openai_base_url: str
    openai_api_key: str
    openai_model: str
    cors_origins: tuple[str, ...]
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-120b"
    guide_root: Path | None = None
    project_id: str = "matrimony-platform"

    @classmethod
    def from_env(cls) -> Settings:
        backend_root = Path(__file__).resolve().parents[1]
        load_env_file(backend_root / ".env")
        origins = tuple(
            part.strip()
            for part in _env("CORS_ORIGINS", "http://localhost:3000").split(",")
            if part.strip()
        )
        manifest_path = Path(_env("MANIFEST_PATH", str(backend_root / "corpus" / "matrimony.yaml")))
        return cls(
            matrimony_platform_root=Path(
                _env(
                    "MATRIMONY_PLATFORM_ROOT",
                    r"d:\WORK\Weoto\Anupam backend\matrimony-platform",
                )
            ),
            matrimony_ui_root=Path(
                _env(
                    "MATRIMONY_UI_ROOT",
                    r"d:\WORK\Weoto\Anupam backend\matrimony-platform-ui",
                )
            ),
            manifest_path=manifest_path,
            qdrant_path=_env("QDRANT_PATH", str(backend_root / "data" / "qdrant")),
            qdrant_url=_env("QDRANT_URL", ""),
            collection_name=_env("COLLECTION_NAME", "matrimony_deployment"),
            embedding_provider=_env("EMBEDDING_PROVIDER", "fastembed"),
            embedding_model=_env("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
            openai_base_url=_env("OPENAI_BASE_URL", "").rstrip("/"),
            openai_api_key=_env("OPENAI_API_KEY", ""),
            openai_model=_env("OPENAI_MODEL", ""),
            cors_origins=origins,
            groq_api_key=_env("GROQ_API_KEY", ""),
            groq_base_url=_env("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/"),
            groq_model=_env("GROQ_MODEL", "openai/gpt-oss-120b"),
            guide_root=Path(_env("GUIDE_ROOT", str(backend_root / "corpus" / "guides"))),
            project_id=_project_id(manifest_path),
        )

    @property
    def llm_enabled(self) -> bool:
        if self.groq_api_key:
            return True
        return bool(self.openai_base_url and self.openai_api_key and self.openai_model)
