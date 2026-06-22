"""Structured logging utilities."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Optional

_logger = logging.getLogger("symphony")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(level: str, msg: str, **ctx: Any) -> None:
    record = {"ts": _now(), "level": level, "msg": msg, **ctx}
    line = json.dumps(record, default=str)
    if level in ("error", "warn"):
        print(line, file=sys.stderr, flush=True)
    else:
        print(line, flush=True)


def info(msg: str, **ctx: Any) -> None:
    _emit("info", msg, **ctx)


def warn(msg: str, **ctx: Any) -> None:
    _emit("warn", msg, **ctx)


def error(msg: str, **ctx: Any) -> None:
    _emit("error", msg, **ctx)


def debug(msg: str, **ctx: Any) -> None:
    _emit("debug", msg, **ctx)


def issue_ctx(issue_id: str, issue_identifier: str) -> dict[str, str]:
    return {"issue_id": issue_id, "issue_identifier": issue_identifier}


def session_ctx(session_id: str) -> dict[str, str]:
    return {"session_id": session_id}
