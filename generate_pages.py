from __future__ import annotations

import html
import json
import os
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from radar.normalizer import BRAZIL_TZ, parse_datetime
from radar.storage import load_state


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
MIN_SEGMENT_RESULTS = 5


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char)).lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")


def _text(value: Any) -> str:
    return html.escape(str(value)) if value not in (None, "") else "Nao informado"


def _opportunity_path(item: dict[str, Any]) -> str:
    return f"editais/{slugify(str(item.get('id') or item.get('numero') or 'oportunidade'))}.html"


def _is_fresh_snapshot(updated: Any, max_age_hours: int, *, now: datetime | None = None) -> bool:
    parsed = parse_datetime(updated)
    if parsed is None:
        return False
    reference = now or datetime.now(BRAZIL_TZ)
    age_seconds = (reference - parsed).total_seconds()
    return -300 <= age_seconds <= max_age_hours * 3600


def _render_detail(item: dict[str, Any], page_title: str) -> str:
    link = item.get("link")
    official_link = (
        f'<a class="button button-primary" href="{html.escape(str(link), quote=True)}" target="_blank" rel="noopener">Abrir no PNCP</a>'
        if isinstance(link, str) and link.startswith("https://pncp.gov.br/")
        else "<p>O PNCP nao informou um link direto validavel para este registro.</p>"
    )
    return f'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(page_title)}</title><meta name="description" content="Detalhes de oportunidade publicada no PNCP.">
<link rel="stylesheet" href="../assets/style.css"></head><body><main class="detail-page">
<a href="../index.html#explorar">&larr; Explorar oportunidades</a><p class="eyebrow">DADO PUBLICO · PNCP</p>
<h1>{_text(item.get('objeto'))}</h1><dl class="detail-grid">
<dt>Orgao comprador</dt><dd>{_text(item.get('orgao'))}</dd><dt>Local</dt><dd>{_text(item.get('municipio'))} / {_text(item.get('uf'))}</dd>
<dt>Numero</dt><dd>{_text(item.get('numero'))}</dd><dt>Modalidade</dt><dd>{_text(item.get('modalidade'))}</dd>
<dt>Valor estimado</dt><dd>{_text(item.get('valor_estimado'))}</dd><dt>Encerramento</dt><dd>{_text(item.get('encerramento'))}</dd>
<dt>Situacao publicada</dt><dd>{_text(item.get('situacao'))}</dd><dt>Atualizacao do PNCP</dt><dd>{_text(item.get('atualizacao'))}</dd>
</dl>{official_link}<p class="source-note">Confirme prazo, documentos e condicoes diretamente no edital oficial. Os dados dependem da publicacao do orgao no PNCP.</p>
</main></body></html>'''


def _render_segment_page(segment: str, uf: str, items: list[dict[str, Any]], updated: str) -> str:
    title = f"Licitacoes de {segment} em {uf}"
    rows = "".join(
        f'<li><a href="../../{_opportunity_path(item)}">{_text(item.get("objeto"))}</a>'
        f'<span>{_text(item.get("municipio"))} · encerra {_text(item.get("encerramento"))}</span></li>'
        for item in items
    )
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} | Radar de Licitacoes</title><meta name="description" content="Oportunidades abertas de {html.escape(segment)} em {html.escape(uf)}, consultadas no PNCP.">
<link rel="stylesheet" href="../../assets/style.css"></head><body><main class="detail-page">
<a href="../../index.html">Radar de Licitacoes</a><p class="eyebrow">OPORTUNIDADES ABERTAS · {html.escape(uf)}</p><h1>{html.escape(title)}</h1>
<p>Dados consultados em {html.escape(updated or 'data nao disponivel')}. Verifique cada prazo e documento na fonte oficial.</p>
<a class="button button-primary" href="../../index.html?keyword={html.escape(slugify(segment), quote=True)}&uf={html.escape(uf, quote=True)}#explorar">Filtrar oportunidades</a>
<ul class="segment-list">{rows}</ul><p class="source-note">Fonte: API de consulta do Portal Nacional de Contratacoes Publicas. A classificacao por segmento e uma busca textual local no objeto da contratacao.</p></main></body></html>'''


def generate() -> dict[str, Any]:
    state = load_state(ROOT / "data" / "radar_data.json")
    updated = state.get("last_successful_collection")
    max_data_age_hours = max(1, int(os.getenv("RADAR_MAX_DATA_AGE_HOURS", "36")))
    fresh = _is_fresh_snapshot(updated, max_data_age_hours)
    items = state.get("opportunities", []) if fresh else []
    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(ROOT / "site", DIST)
    data_dir = DIST / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    public_data = {
        "last_successful_collection": updated,
        "collection_status": "available" if fresh else "stale" if updated else "not_run",
        "max_data_age_hours": max_data_age_hours,
        "items": items,
    }
    (data_dir / "opportunities.json").write_text(json.dumps(public_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metrics = state.get("alert_metrics", {})
    public_metrics = {
        "open_opportunities": len(items) if fresh else None,
        "telegram_messages_sent": metrics.get("sent_messages", 0),
        "visitors": None,
        "registrations": None,
        "active_users": None,
        "as_of": updated,
        "max_data_age_hours": max_data_age_hours,
    }
    (data_dir / "metrics.json").write_text(json.dumps(public_metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    detail_urls: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        relative_path = _opportunity_path(item)
        target = DIST / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_render_detail(item, f"{item.get('objeto') or 'Oportunidade'} | Radar de Licitacoes"), encoding="utf-8")
        detail_urls.append(relative_path)

    segment = os.getenv("RADAR_KEYWORD", "tecnologia").strip() or "Oportunidades"
    uf = os.getenv("RADAR_UF", "SC").strip().upper()
    segment_items = [item for item in items if str(item.get("uf") or "").upper() == uf]
    segment_items = [item for item in segment_items if slugify(segment) in slugify(str(item.get("objeto") or ""))]
    segment_path: str | None = None
    if len(segment_items) >= MIN_SEGMENT_RESULTS:
        segment_slug = f"{slugify(segment)}-{slugify(uf)}"
        segment_path = f"segmentos/{segment_slug}/index.html"
        target = DIST / segment_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_render_segment_page(segment, uf, segment_items, updated), encoding="utf-8")

    site_url = os.getenv("RADAR_SITE_URL", "").strip().rstrip("/")
    if site_url:
        urls = ["index.html", *detail_urls]
        if segment_path:
            urls.append(segment_path)
        locations = "".join(f"<url><loc>{html.escape(site_url + '/' + path)}</loc></url>" for path in urls)
        sitemap = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locations}</urlset>'
        (DIST / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    else:
        sitemap_path = DIST / "sitemap.xml"
        if sitemap_path.exists():
            sitemap_path.unlink()
        robots_path = DIST / "robots.txt"
        if robots_path.exists():
            robots_path.write_text(
                "\n".join(
                    line for line in robots_path.read_text(encoding="utf-8").splitlines()
                    if not line.lower().startswith("sitemap:")
                ) + "\n",
                encoding="utf-8",
            )

    print(f"Site gerado: {len(items)} oportunidades; {len(detail_urls)} detalhes; pagina de segmento={'sim' if segment_path else 'nao (menos de 5 resultados)'}.")
    return public_data


if __name__ == "__main__":
    generate()