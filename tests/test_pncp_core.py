from __future__ import annotations

import json
import unittest
from datetime import date, datetime, timedelta, timezone
from email.message import Message
from urllib.error import HTTPError, URLError

from radar.filters import filter_records, is_open
from radar.normalizer import normalize, official_url, parse_datetime
from radar.pncp_client import IncompleteCollectionError, PNCPClient, PNCPError


NOW = datetime(2026, 10, 17, 12, tzinfo=timezone(timedelta(hours=-3)))


def sample(**overrides):
    record = {
        "numeroControlePNCP": "12345678000199-1-000123/2026",
        "anoCompra": 2026,
        "sequencialCompra": 123,
        "numeroCompra": "17/2026",
        "objetoCompra": "Aquisicao de computadores",
        "orgaoEntidade": {"razaoSocial": "Municipio de Florianopolis", "cnpj": "12345678000199"},
        "unidadeOrgao": {"ufSigla": "SC", "municipioNome": "Florianopolis"},
        "valorTotalEstimado": 25000,
        "dataEncerramentoProposta": "2026-10-20T15:00:00",
        "dataAtualizacaoGlobal": "2026-10-16T10:00:00",
        "modalidadeNome": "Pregao - Eletronico",
        "situacaoCompraId": 1,
        "situacaoCompraNome": "Divulgada no PNCP",
    }
    record.update(overrides)
    return record


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class PNCPClientTests(unittest.TestCase):
    def client_for(self, responses, *, sleeper=lambda _seconds: None, retries=0):
        calls = []

        def opener(request, timeout):
            calls.append(request.full_url)
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return FakeResponse(response)

        return PNCPClient(opener=opener, sleeper=sleeper, retries=retries, min_request_interval=0), calls

    def test_valid_response_and_required_query_parameters(self):
        client, calls = self.client_for([{"data": [sample()], "totalPaginas": 1}])
        result = client.collect_open_proposals(deadline_until=date(2026, 10, 31), uf="sc", page_size=10)
        self.assertEqual(len(result.records), 1)
        self.assertIn("dataFinal=20261031", calls[0])
        self.assertIn("pagina=1", calls[0])
        self.assertIn("tamanhoPagina=10", calls[0])
        self.assertIn("uf=SC", calls[0])

    def test_empty_response_is_a_successful_empty_collection(self):
        client, _ = self.client_for([{"data": [], "totalPaginas": 0}])
        result = client.collect_open_proposals(deadline_until=date(2026, 10, 31))
        self.assertEqual(result.records, [])
        self.assertEqual(result.pages_fetched, 1)

    def test_pagination_and_duplicate_removal(self):
        record = sample()
        client, calls = self.client_for([
            {"data": [record], "totalPaginas": 2},
            {"data": [record, sample(numeroControlePNCP="12345678000199-1-000124/2026")], "totalPaginas": 2},
        ])
        result = client.collect_open_proposals(deadline_until=date(2026, 10, 31))
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.pages_fetched, 2)
        self.assertIn("pagina=2", calls[1])

    def test_distinct_records_without_identifiers_are_not_collapsed(self):
        client, _ = self.client_for([{"data": [{"objetoCompra": "A"}, {"objetoCompra": "B"}], "totalPaginas": 1}])
        result = client.collect_open_proposals(deadline_until=date(2026, 10, 31))
        self.assertEqual(len(result.records), 2)

    def test_page_cap_does_not_return_partial_success(self):
        client, _ = self.client_for([{"data": [sample()], "totalPaginas": 3}])
        with self.assertRaises(IncompleteCollectionError):
            client.collect_open_proposals(deadline_until=date(2026, 10, 31), max_pages=1)

    def test_http_429_respects_retry_after(self):
        headers = Message()
        headers["Retry-After"] = "120"
        waits = []
        client, _ = self.client_for([
            HTTPError("https://pncp.gov.br", 429, "Too Many Requests", headers, None),
            {"data": [], "totalPaginas": 0},
        ], sleeper=waits.append, retries=1)
        result = client.collect_open_proposals(deadline_until=date(2026, 10, 31))
        self.assertEqual(result.records, [])
        self.assertIn(120, waits)

    def test_http_429_retry_after_above_limit_defers_without_early_retry(self):
        headers = Message()
        headers["Retry-After"] = "900"
        client, _ = self.client_for([
            HTTPError("https://pncp.gov.br", 429, "Too Many Requests", headers, None),
        ], retries=3)
        with self.assertRaisesRegex(PNCPError, "Tente novamente depois"):
            client.collect_open_proposals(deadline_until=date(2026, 10, 31))

    def test_connection_failure_is_not_an_empty_result(self):
        client, _ = self.client_for([URLError("offline")], retries=0)
        with self.assertRaises(PNCPError):
            client.collect_open_proposals(deadline_until=date(2026, 10, 31))

    def test_invalid_response_shape_fails(self):
        client, _ = self.client_for([{"totalPaginas": 1}])
        with self.assertRaises(PNCPError):
            client.collect_open_proposals(deadline_until=date(2026, 10, 31))

    def test_missing_page_count_is_not_treated_as_empty_collection(self):
        client, _ = self.client_for([{"data": []}])
        with self.assertRaises(PNCPError):
            client.collect_open_proposals(deadline_until=date(2026, 10, 31))

    def test_records_with_zero_reported_pages_are_rejected(self):
        client, _ = self.client_for([{"data": [sample()], "totalPaginas": 0}])
        with self.assertRaisesRegex(PNCPError, "totalPaginas e zero"):
            client.collect_open_proposals(deadline_until=date(2026, 10, 31))


class NormalizerAndFilterTests(unittest.TestCase):
    def test_normalizes_nullable_fields_and_official_link(self):
        item = normalize(sample(valorTotalEstimado=None, objetoCompra=None))
        self.assertIsNone(item["valor_estimado"])
        self.assertIsNone(item["objeto"])
        self.assertEqual(item["link"], "https://pncp.gov.br/app/editais/12345678000199/2026/123")

    def test_invalid_dates_and_missing_links_are_safe(self):
        self.assertIsNone(parse_datetime("not-a-date"))
        self.assertIsNone(parse_datetime(None))
        self.assertIsNone(official_url({"numeroControlePNCP": "bad"}))

    def test_filters_by_keyword_uf_and_value(self):
        records = [sample(), sample(numeroControlePNCP="other", objetoCompra="Material de limpeza", valorTotalEstimado=400)]
        result = filter_records(records, keyword="computadores", uf="sc", min_value=1000, now=NOW)
        self.assertEqual([item["id"] for item in result], [sample()["numeroControlePNCP"]])

    def test_expired_or_unparseable_deadlines_are_not_open(self):
        self.assertFalse(is_open(sample(dataEncerramentoProposta="2026-10-17T11:59:00"), now=NOW))
        self.assertFalse(is_open(sample(dataEncerramentoProposta="invalid"), now=NOW))

    def test_status_can_be_filtered_and_closed_status_is_excluded(self):
        self.assertFalse(is_open(sample(situacaoCompraNome="Encerrada"), now=NOW))
        self.assertTrue(is_open(sample(situacaoCompraId=2), now=NOW))
        self.assertEqual(len(filter_records([sample()], situation="Divulgada", now=NOW)), 1)


if __name__ == "__main__":
    unittest.main()