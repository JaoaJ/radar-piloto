"""Local filtering applied after the broad PNCP open-proposal query."""

from __future__ import annotations

import unicodedata
from datetime import datetime
from typing import Any, Iterable

from .normalizer import BRAZIL_TZ, normalize


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char)).casefold()


def is_open(record: dict[str, Any], *, now: datetime | None = None) -> bool:
    item = normalize(record)
    deadline = item["encerramento"]
    if deadline is None:
        return False
    reference = now or datetime.now(BRAZIL_TZ)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=BRAZIL_TZ)
    if deadline <= reference:
        return False
    status = _fold(item["situacao"])
    if status and any(term in status for term in ("encerrad", "homologad", "cancelad", "revogad")):
        return False
    return True


def filter_records(
    records: Iterable[dict[str, Any]],
    *,
    keyword: str | None = None,
    uf: str | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    deadline_after: datetime | None = None,
    deadline_before: datetime | None = None,
    situation: str | None = None,
    now: datetime | None = None,
    only_open: bool = True,
) -> list[dict[str, Any]]:
    normalized_keyword = _fold(keyword).strip()
    result: list[dict[str, Any]] = []
    for record in records:
        item = normalize(record)
        if only_open and not is_open(record, now=now):
            continue
        if uf and _fold(item["uf"]) != _fold(uf):
            continue
        if normalized_keyword:
            search_text = _fold(" ".join(str(item.get(key) or "") for key in ("objeto", "orgao", "modalidade")))
            if normalized_keyword not in search_text:
                continue
        value = item["valor_estimado"]
        if min_value is not None and (value is None or value < min_value):
            continue
        if max_value is not None and (value is None or value > max_value):
            continue
        deadline = item["encerramento"]
        if deadline_after and (deadline is None or deadline < deadline_after):
            continue
        if deadline_before and (deadline is None or deadline > deadline_before):
            continue
        if situation and _fold(situation) not in _fold(item["situacao"]):
            continue
        result.append(item)
    return result