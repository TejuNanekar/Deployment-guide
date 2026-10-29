"""Structured logs for ingest and query. Document text is not logged."""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("deployment_assistant")


def log_event(event: str, **fields: object) -> None:
    safe = {key: value for key, value in fields.items() if key not in {"text", "command", "api_key", "excerpt"}}
    logger.info("%s %s", event, json.dumps(safe, default=str, sort_keys=True))
