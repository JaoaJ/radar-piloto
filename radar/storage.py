"""Atomic JSON storage for the small, scheduled MVP."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


EMPTY_STATE: dict[str, Any] = {
    "schema_version": 1,
    "last_successful_collection": None,
    "opportunities": [],
    "seen_ids": [],
    "sent_ids": [],
    "notification_failures": {},
}


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {**EMPTY_STATE}
    try:
        with path.open("r", encoding="utf-8") as stream:
            state = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Estado local invalido em {path}: {exc}") from exc
    if not isinstance(state, dict) or not isinstance(state.get("opportunities", []), list):
        raise RuntimeError(f"Formato de estado local invalido em {path}")
    return {**EMPTY_STATE, **state}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as stream:
            temporary_path = stream.name
            json.dump(state, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary_path, path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)