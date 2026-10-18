"""Telegram Bot API notifications; credentials are read only from environment."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TELEGRAM_API = "https://api.telegram.org"


def select_notification_items(
    items: list[dict[str, Any]],
    *,
    seen_ids: set[str],
    sent_ids: set[str],
    failed_ids: set[str],
) -> list[dict[str, Any]]:
    return [
        item
        for item in items
        if item.get("id")
        and item["id"] not in sent_ids
        and (item["id"] not in seen_ids or item["id"] in failed_ids)
    ]


def format_opportunity(item: dict[str, Any]) -> str:
    deadline = item.get("encerramento")
    if isinstance(deadline, str):
        try:
            deadline = datetime.fromisoformat(deadline)
        except ValueError:
            deadline = None
    deadline_text = deadline.strftime("%d/%m/%Y %H:%M") if isinstance(deadline, datetime) else "Prazo nao informado"
    amount = item.get("valor_estimado")
    amount_text = f"R$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if isinstance(amount, (int, float)) else "Nao informado"
    title = str(item.get("objeto") or "Objeto nao informado").strip()
    if len(title) > 480:
        title = title[:477].rstrip() + "..."
    details = " · ".join(part for part in (item.get("orgao"), item.get("municipio"), item.get("uf")) if part)
    lines = [f"{title}", details or "Orgao/local nao informado", f"Prazo: {deadline_text} · Estimado: {amount_text}"]
    if item.get("link"):
        lines.append(str(item["link"]))
    return "\n".join(lines)


def build_digest(items: list[dict[str, Any]], *, limit: int = 10) -> list[str]:
    if limit < 1:
        raise ValueError("O limite de oportunidades deve ser maior que zero")
    ordered = sorted(items, key=lambda item: item.get("encerramento") or "9999")
    selected = ordered[:limit]
    if not selected:
        return ["Radar de Licitacoes: nenhuma oportunidade nova no periodo."]
    messages: list[str] = []
    for start in range(0, len(selected), 5):
        batch = selected[start : start + 5]
        header = f"Radar de Licitacoes · {len(batch)} oportunidade(s)"
        messages.append(header + "\n\n" + "\n\n".join(format_opportunity(item) for item in batch))
    return messages


class TelegramNotifier:
    def __init__(
        self,
        token: str,
        chat_id: str,
        *,
        timeout: float = 20,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        if not token.strip() or not chat_id.strip():
            raise ValueError("Token e chat_id do Telegram sao obrigatorios")
        self.token = token
        self.chat_id = chat_id
        self.timeout = timeout
        self.opener = opener

    def send(
        self,
        items: list[dict[str, Any]],
        *,
        limit: int = 10,
        on_batch_sent: Callable[[list[dict[str, Any]]], None] | None = None,
    ) -> int:
        ordered = sorted(items, key=lambda item: item.get("encerramento") or "9999")[:limit]
        messages = build_digest(ordered, limit=limit)
        url = f"{TELEGRAM_API}/bot{self.token}/sendMessage"
        for index, message in enumerate(messages):
            body = json.dumps({"chat_id": self.chat_id, "text": message, "disable_web_page_preview": True}).encode()
            request = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    result = json.loads(response.read().decode("utf-8"))
            except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Falha ao enviar digest Telegram: {type(exc).__name__}") from exc
            if not isinstance(result, dict) or result.get("ok") is not True:
                raise RuntimeError("Telegram rejeitou o digest")
            if on_batch_sent and ordered:
                on_batch_sent(ordered[index * 5 : (index + 1) * 5])
        return len(messages)