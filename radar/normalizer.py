"""Convert PNCP response objects into the site's stable public shape."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any


BRAZIL_TZ = timezone(timedelta(hours=-3))
PNCP_BASE = "https://pncp.gov.br"
CONTROL_NUMBER = re.compile(r"^(\d{14})-\d-(\d{6})/(\d{4})$")


def parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=BRAZIL_TZ) if parsed.tzinfo is None else parsed


def official_url(record: dict[str, Any]) -> str | None:
    control = str(record.get("numeroControlePNCP") or "")
    match = CONTROL_NUMBER.fullmatch(control)
    if match:
        cnpj, sequence, year = match.groups()
        return f"{PNCP_BASE}/app/editais/{cnpj}/{year}/{int(sequence)}"

    organization = record.get("orgaoEntidade") or {}
    cnpj = str(organization.get("cnpj") or "")
    year = record.get("anoCompra")
    sequence = record.get("sequencialCompra")
    if cnpj.isdigit() and len(cnpj) == 14 and year and sequence:
        return f"{PNCP_BASE}/app/editais/{cnpj}/{year}/{int(sequence)}"
    source_link = record.get("linkSistemaOrigem")
    if isinstance(source_link, str) and source_link.startswith("https://"):
        return source_link
    return None


def normalize(record: dict[str, Any]) -> dict[str, Any]:
    organization = record.get("orgaoEntidade") or {}
    unit = record.get("unidadeOrgao") or {}
    value = record.get("valorTotalEstimado")
    try:
        value = float(value) if value is not None else None
    except (TypeError, ValueError):
        value = None

    return {
        "id": str(record.get("numeroControlePNCP") or "").strip() or None,
        "numero_controle": record.get("numeroControlePNCP"),
        "numero": record.get("numeroCompra"),
        "objeto": record.get("objetoCompra"),
        "orgao": organization.get("razaoSocial"),
        "uf": unit.get("ufSigla"),
        "municipio": unit.get("municipioNome"),
        "valor_estimado": value,
        "encerramento": parse_datetime(record.get("dataEncerramentoProposta")),
        "modalidade": record.get("modalidadeNome"),
        "situacao": record.get("situacaoCompraNome"),
        "situacao_id": str(record.get("situacaoCompraId") or ""),
        "atualizacao": parse_datetime(
            record.get("dataAtualizacaoGlobal") or record.get("dataAtualizacao")
        ),
        "link": official_url(record),
        "ano": record.get("anoCompra"),
        "sequencial": record.get("sequencialCompra"),
    }