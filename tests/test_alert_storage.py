from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from generate_pages import _is_fresh_snapshot
from radar.storage import load_state, save_state
from radar.telegram_notifier import TelegramNotifier, build_digest, select_notification_items


class StorageAndAlertTests(unittest.TestCase):
    def test_snapshot_freshness_rejects_stale_and_future_timestamps(self):
        now = datetime(2026, 10, 17, 12, tzinfo=timezone(timedelta(hours=-3)))
        self.assertTrue(_is_fresh_snapshot("2026-10-17T10:00:00-03:00", 36, now=now))
        self.assertFalse(_is_fresh_snapshot("2026-10-15T12:00:00-03:00", 36, now=now))
        self.assertFalse(_is_fresh_snapshot("2026-10-18T12:00:00-03:00", 36, now=now))
        self.assertFalse(_is_fresh_snapshot(None, 36, now=now))

    def test_state_round_trips_as_utf8_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "state.json"
            state = load_state(path)
            state["opportunities"] = [{"objeto": "Saude publica"}]
            save_state(path, state)
            self.assertEqual(load_state(path)["opportunities"][0]["objeto"], "Saude publica")

    def test_digest_orders_by_deadline_and_handles_empty(self):
        items = [
            {"id": "late", "objeto": "Depois", "encerramento": "2026-10-20T10:00:00-03:00"},
            {"id": "soon", "objeto": "Antes", "encerramento": "2026-10-18T10:00:00-03:00"},
        ]
        digest = build_digest(items, limit=1)
        self.assertIn("Antes", digest[0])
        self.assertEqual(build_digest([], limit=5), ["Radar de Licitacoes: nenhuma oportunidade nova no periodo."])

    def test_only_new_or_failed_unsent_items_are_selected(self):
        items = [{"id": "new"}, {"id": "sent"}, {"id": "failed"}, {"id": "known"}]
        selected = select_notification_items(
            items,
            seen_ids={"sent", "failed", "known"},
            sent_ids={"sent"},
            failed_ids={"failed"},
        )
        self.assertEqual([item["id"] for item in selected], ["new", "failed"])

    def test_telegram_send_uses_api_payload_and_returns_message_count(self):
        requests = []

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"ok":true,"result":{"message_id":1}}'

        def opener(request, timeout):
            requests.append((request.full_url, request.data, timeout))
            return Response()

        notifier = TelegramNotifier("test-token", "test-chat", opener=opener)
        count = notifier.send(
            [{"id": "sample", "objeto": "Computadores", "link": "https://pncp.gov.br/app/editais/1/2026/1"}],
            limit=3,
        )
        self.assertEqual(count, 1)
        self.assertIn("/bottest-token/sendMessage", requests[0][0])
        self.assertIn(b"Computadores", requests[0][1])
        self.assertIn(b"https://pncp.gov.br/app/editais/1/2026/1", requests[0][1])

    def test_telegram_reports_each_successful_batch_before_later_failure(self):
        sent_batches = []
        responses = iter([
            b'{"ok":true}',
            RuntimeError("temporary failure"),
        ])

        class Response:
            def __init__(self, body):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return self.body

        def opener(_request, timeout):
            response = next(responses)
            if isinstance(response, Exception):
                raise response
            return Response(response)

        items = [{"id": str(index), "objeto": f"Oportunidade {index}"} for index in range(6)]
        notifier = TelegramNotifier("test-token", "test-chat", opener=opener)
        with self.assertRaises(RuntimeError):
            notifier.send(items, on_batch_sent=sent_batches.append)
        self.assertEqual([[item["id"] for item in batch] for batch in sent_batches], [["0", "1", "2", "3", "4"]])


if __name__ == "__main__":
    unittest.main()