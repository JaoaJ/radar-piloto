"""Small, dependency-free client for the official PNCP consultation API."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_ROOT = "https://pncp.gov.br/api/consulta/v1"
MAX_PAGE_SIZE = 50


class PNCPError(RuntimeError):
    """Base error for API and collection failures."""


class PNCPResponseError(PNCPError):
    """The API returned an invalid response."""


class IncompleteCollectionError(PNCPError):
    """A configured page cap would make the collection incomplete."""


class PNCPRateLimitError(PNCPError):
    """The API requested a retry delay longer than this run may wait."""


@dataclass(frozen=True)
class Collection:
    records: list[dict[str, Any]]
    pages_fetched: int
    total_pages: int


class PNCPClient:
    def __init__(
        self,
        *,
        timeout: float = 20,
        retries: int = 4,
        backoff_seconds: float = 1,
        max_backoff_seconds: float = 30,
        max_retry_after_seconds: float = 600,
        min_request_interval: float = 0.35,
        opener: Callable[..., Any] = urlopen,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self.backoff_seconds = backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.max_retry_after_seconds = max_retry_after_seconds
        self.min_request_interval = min_request_interval
        self.opener = opener
        self.sleeper = sleeper
        self.clock = clock
        self._last_request_at: float | None = None

    def _wait_for_rate_limit(self) -> None:
        if self._last_request_at is not None:
            elapsed = self.clock() - self._last_request_at
            remaining = self.min_request_interval - elapsed
            if remaining > 0:
                self.sleeper(remaining)
        self._last_request_at = self.clock()

    def _get_page(self, url: str) -> dict[str, Any]:
        for attempt in range(self.retries + 1):
            self._wait_for_rate_limit()
            request = Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "RadarDeLicitacoes/0.1 (consulta de dados publicos)",
                },
            )
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    if getattr(response, "status", 200) == 204:
                        return {"data": [], "totalPaginas": 0}
                    body = response.read()
                try:
                    result = json.loads(body.decode("utf-8-sig"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise PNCPResponseError("Resposta da API nao contem JSON valido") from exc
                if not isinstance(result, dict):
                    raise PNCPResponseError("Resposta da API deve ser um objeto JSON")
                return result
            except HTTPError as exc:
                if exc.code != 429 and not 500 <= exc.code <= 599:
                    raise PNCPError(f"PNCP respondeu HTTP {exc.code}") from exc
                if attempt >= self.retries:
                    raise PNCPError(f"PNCP continuou respondendo HTTP {exc.code} apos tentativas") from exc
                headers = exc.headers or {}
                retry_after = self._retry_after(headers.get("Retry-After"))
                if retry_after is not None and retry_after > self.max_retry_after_seconds:
                    raise PNCPRateLimitError(
                        f"PNCP solicitou espera de {retry_after:g}s; limite local por tentativa "
                        f"e {self.max_retry_after_seconds:g}s. Tente novamente depois."
                    ) from exc
                self.sleeper(retry_after if retry_after is not None else self._backoff(attempt))
            except (TimeoutError, URLError, ConnectionError, OSError) as exc:
                if attempt >= self.retries:
                    raise PNCPError(f"Falha de conexao com o PNCP: {exc}") from exc
                self.sleeper(self._backoff(attempt))
        raise PNCPError("Falha inesperada ao consultar o PNCP")

    def _backoff(self, attempt: int) -> float:
        return min(self.backoff_seconds * (2**attempt), self.max_backoff_seconds)

    def _retry_after(self, value: str | None) -> float | None:
        if not value:
            return None
        try:
            seconds = float(value)
            return seconds if seconds >= 0 else None
        except ValueError:
            try:
                seconds = parsedate_to_datetime(value).timestamp() - time.time()
                return max(seconds, 0)
            except (TypeError, ValueError, OverflowError):
                return None

    def collect_open_proposals(
        self,
        *,
        deadline_until: date,
        uf: str | None = None,
        page_size: int = MAX_PAGE_SIZE,
        max_pages: int = 100,
    ) -> Collection:
        if not 10 <= page_size <= MAX_PAGE_SIZE:
            raise ValueError(f"tamanhoPagina deve estar entre 10 e {MAX_PAGE_SIZE}")
        if max_pages < 1:
            raise ValueError("max_pages deve ser maior que zero")

        records: list[dict[str, Any]] = []
        seen: set[str] = set()
        total_pages: int | None = None
        for page in range(1, max_pages + 1):
            params = {
                "dataFinal": deadline_until.strftime("%Y%m%d"),
                "pagina": str(page),
                "tamanhoPagina": str(page_size),
            }
            if uf:
                params["uf"] = uf.upper()
            result = self._get_page(f"{API_ROOT}/contratacoes/proposta?{urlencode(params)}")
            page_records = result.get("data")
            if not isinstance(page_records, list):
                raise PNCPResponseError("Campo 'data' ausente ou invalido na resposta")
            reported_pages = result.get("totalPaginas")
            if not isinstance(reported_pages, int) or reported_pages < 0:
                raise PNCPResponseError("Campo 'totalPaginas' invalido na resposta")
            if reported_pages == 0 and page_records:
                raise PNCPResponseError("A resposta contem registros, mas totalPaginas e zero")
            total_pages = max(total_pages or reported_pages, reported_pages)
            for record in page_records:
                if not isinstance(record, dict):
                    raise PNCPResponseError("Registro da API nao e um objeto JSON")
                key = str(record.get("numeroControlePNCP") or "").strip()
                if not key:
                    parts = [
                        str(record.get(name) or "")
                        for name in ("anoCompra", "sequencialCompra", "numeroCompra")
                    ]
                    key = "|".join(parts) if any(parts) else ""
                if not key or key not in seen:
                    if key:
                        seen.add(key)
                    records.append(record)
            if page >= total_pages or not page_records:
                return Collection(records, page, total_pages)

        assert total_pages is not None
        raise IncompleteCollectionError(
            f"Limite de {max_pages} paginas atingido; a API informou {total_pages}. "
            "A coleta foi marcada como incompleta."
        )