from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from radar.filters import filter_records
from radar.normalizer import BRAZIL_TZ
from radar.pncp_client import PNCPClient
from radar.storage import load_state, save_state
from radar.telegram_notifier import TelegramNotifier, build_digest, select_notification_items


ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "data" / "radar_data.json"


def _optional_float(name: str) -> float | None:
    value = os.getenv(name, "").strip()
    return float(value) if value else None


def run() -> dict[str, Any]:
    now = datetime.now(BRAZIL_TZ)
    uf = os.getenv("RADAR_UF", "SC").strip().upper() or None
    days_ahead = max(1, int(os.getenv("RADAR_DAYS_AHEAD", "30")))
    max_pages = max(1, int(os.getenv("RADAR_MAX_PAGES", "100")))
    keyword = os.getenv("RADAR_KEYWORD", "tecnologia").strip()
    limit = max(1, int(os.getenv("RADAR_MAX_ALERTS", "10")))
    state = load_state(STATE_PATH)

    collection = PNCPClient().collect_open_proposals(
        deadline_until=(now + timedelta(days=days_ahead)).date(),
        uf=uf,
        max_pages=max_pages,
    )
    open_opportunities = filter_records(
        collection.records,
        uf=uf,
        now=now,
    )
    alert_opportunities = filter_records(
        collection.records,
        keyword=keyword or None,
        uf=uf,
        min_value=_optional_float("RADAR_MIN_VALUE"),
        max_value=_optional_float("RADAR_MAX_VALUE"),
        now=now,
    )
    for items in (open_opportunities, alert_opportunities):
        items.sort(key=lambda item: item.get("encerramento") or datetime.max.replace(tzinfo=BRAZIL_TZ))
        for item in items:
            for field in ("encerramento", "atualizacao"):
                if isinstance(item[field], datetime):
                    item[field] = item[field].isoformat()

    completed_at = datetime.now(BRAZIL_TZ)
    known_ids = set(state.get("seen_ids", []))
    sent_ids = set(state.get("sent_ids", []))
    previous_failures = dict(state.get("notification_failures", {}))
    pending_items = select_notification_items(
        alert_opportunities,
        seen_ids=known_ids,
        sent_ids=sent_ids,
        failed_ids=set(previous_failures),
    )
    failures = previous_failures.copy()
    messages_sent = 0
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    send_empty = os.getenv("RADAR_SEND_EMPTY", "false").casefold() == "true"
    should_send = bool(pending_items) or (send_empty and not alert_opportunities)

    if token and chat_id and should_send:
        delivery_stats = {"messages": 0}

        def mark_batch_sent(batch: list[dict[str, Any]]) -> None:
            delivery_stats["messages"] += 1
            for item in batch:
                if item.get("id"):
                    sent_ids.add(item["id"])
                    failures.pop(item["id"], None)

        try:
            messages_sent = TelegramNotifier(token, chat_id).send(
                pending_items,
                limit=limit,
                on_batch_sent=mark_batch_sent,
            )
        except RuntimeError as exc:
            messages_sent = delivery_stats["messages"]
            failures.update(
                {
                    item["id"]: str(exc)
                    for item in pending_items
                    if item.get("id") and item["id"] not in sent_ids
                }
            )
    elif should_send:
        preview_path = ROOT / "data" / "last_digest.txt"
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_text("\n\n---\n\n".join(build_digest(pending_items, limit=limit)), encoding="utf-8")
        if pending_items:
            failures.update({item["id"]: "Telegram nao configurado; pendente." for item in pending_items if item.get("id")})

    state.update(
        {
            "last_successful_collection": completed_at.isoformat(),
            "opportunities": open_opportunities,
            "seen_ids": sorted(known_ids | {item["id"] for item in alert_opportunities if item.get("id")}),
            "sent_ids": sorted(sent_ids),
            "notification_failures": failures,
            "collection": {
                "pages_fetched": collection.pages_fetched,
                "total_pages": collection.total_pages,
                "raw_records": len(collection.records),
                "open_records": len(open_opportunities),
                "matching_alert_records": len(alert_opportunities),
                "keyword": keyword or None,
                "uf": uf,
            },
            "alert_metrics": {
                "sent_messages": int(state.get("alert_metrics", {}).get("sent_messages", 0)) + messages_sent,
                "sent_opportunities": len(sent_ids),
            },
        }
    )
    save_state(STATE_PATH, state)
    print(
        f"Coleta concluida: {len(collection.records)} registros brutos, "
        f"{len(open_opportunities)} oportunidades abertas, "
        f"{len(alert_opportunities)} compativeis com alertas, "
        f"{collection.pages_fetched}/{collection.total_pages} paginas."
    )
    if failures and token and chat_id:
        print(f"::warning::Falha no envio Telegram para {len(failures)} oportunidade(s); registrada para nova tentativa.")
    if should_send and not token:
        print("Telegram nao configurado; previa salva e oportunidades pendentes preservadas.")
    return state


if __name__ == "__main__":
    run()