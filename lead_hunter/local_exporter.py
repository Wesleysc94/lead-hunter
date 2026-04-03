"""Local filesystem exports for qualified leads."""

from __future__ import annotations

import csv
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from . import config

EXPORT_DIR = config.BASE_DIR / "exports"


def _status_order(status: str) -> int:
    """Return the sort order for lead status."""
    return {"HOT": 0, "WARM": 1, "COLD": 2, "SKIP": 3}.get(status, 99)


def _sorted_leads(leads: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort leads by status and descending score."""
    return sorted(
        leads,
        key=lambda lead: (_status_order(str(lead.get("status", ""))), -int(lead.get("score") or 0)),
    )


def _csv_rows(leads: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten lead data into CSV-friendly rows."""
    rows: list[dict[str, Any]] = []
    for lead in _sorted_leads(leads):
        rows.append(
            {
                "status": lead.get("status", ""),
                "score": lead.get("score", ""),
                "nome": lead.get("name", ""),
                "categoria": lead.get("category", ""),
                "bairro": lead.get("neighborhood", ""),
                "cidade": lead.get("city", ""),
                "telefone": lead.get("phone", ""),
                "instagram": lead.get("instagram_username", ""),
                "tipo_link": lead.get("link_type_label", lead.get("link_type", "")),
                "seguidores": lead.get("followers_count", ""),
                "engajamento": lead.get("engagement_rate", ""),
                "avaliacoes_google": lead.get("google_reviews", ""),
                "rating_google": lead.get("google_rating", ""),
                "ultimo_post_dias": lead.get("last_post_days", ""),
                "pontos_fortes": " | ".join(lead.get("key_strengths") or []),
                "mensagem_whatsapp": lead.get("whatsapp_message", ""),
                "mensagem_instagram_dm": lead.get("instagram_dm", ""),
                "maps_url": lead.get("maps_url", ""),
                "website": lead.get("website", ""),
                "coletado_em": lead.get("collected_at", ""),
            }
        )
    return rows


def _write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    """Write qualified leads to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = list(rows[0].keys()) if rows else [
        "status",
        "score",
        "nome",
        "categoria",
        "bairro",
        "cidade",
        "telefone",
        "instagram",
        "tipo_link",
        "seguidores",
        "engajamento",
        "avaliacoes_google",
        "rating_google",
        "ultimo_post_dias",
        "pontos_fortes",
        "mensagem_whatsapp",
        "mensagem_instagram_dm",
        "maps_url",
        "website",
        "coletado_em",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _write_html(path: Path, leads: Sequence[dict[str, Any]], summary: dict[str, Any]) -> None:
    """Write a simple HTML report for manual review."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cards: list[str] = []
    for lead in _sorted_leads(leads):
        cards.append(
            f"""
            <article class="lead-card {html.escape(str(lead.get('status', '')).lower())}">
              <header>
                <h2>{html.escape(str(lead.get("name", "")))}</h2>
                <div class="meta">{html.escape(str(lead.get("status_display", lead.get("status", ""))))} · Score {html.escape(str(lead.get("score", "")))}</div>
              </header>
              <p><strong>Local:</strong> {html.escape(str(lead.get("neighborhood", "")))} - {html.escape(str(lead.get("city", "")))}</p>
              <p><strong>Instagram:</strong> @{html.escape(str(lead.get("instagram_username", "")))}</p>
              <p><strong>Link atual:</strong> {html.escape(str(lead.get("link_type_label", lead.get("link_type", ""))))}</p>
              <p><strong>Pontos fortes:</strong> {html.escape(" | ".join(lead.get("key_strengths") or []))}</p>
              <p><strong>Mensagem WhatsApp:</strong><br>{html.escape(str(lead.get("whatsapp_message", ""))).replace(chr(10), "<br>")}</p>
              <p class="links">
                <a href="{html.escape(str(lead.get("maps_url", "")))}" target="_blank">Abrir no Maps</a>
              </p>
            </article>
            """.strip()
        )

    html_text = f"""
    <!doctype html>
    <html lang="pt-BR">
      <head>
        <meta charset="utf-8">
        <title>Leads Qualificados</title>
        <style>
          body {{ font-family: Arial, sans-serif; margin: 32px; background: #f8fafc; color: #111827; }}
          h1 {{ margin-bottom: 8px; }}
          .summary {{ margin-bottom: 24px; }}
          .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }}
          .lead-card {{ background: white; border-radius: 12px; padding: 18px; box-shadow: 0 4px 14px rgba(0,0,0,0.08); }}
          .lead-card.hot {{ border-left: 6px solid #dc2626; }}
          .lead-card.warm {{ border-left: 6px solid #d97706; }}
          .meta {{ color: #4b5563; font-size: 14px; margin-bottom: 12px; }}
          .links a {{ color: #2563eb; text-decoration: none; }}
        </style>
      </head>
      <body>
        <h1>Leads Qualificados</h1>
        <div class="summary">
          <p>Encontrados: {summary.get("found", 0)} | Processados: {summary.get("processed", 0)} | Qualificados: {summary.get("qualified", 0)} | HOT: {summary.get("hot", 0)} | WARM: {summary.get("warm", 0)}</p>
          <p>Gerado em {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}</p>
        </div>
        <section class="grid">
          {"".join(cards) if cards else "<p>Nenhum lead qualificado nesta rodada.</p>"}
        </section>
      </body>
    </html>
    """.strip()
    path.write_text(html_text, encoding="utf-8")


def export_local_files(leads: Sequence[dict[str, Any]], summary: dict[str, Any]) -> dict[str, str]:
    """Export CSV, JSON snapshot, and HTML report to the local filesystem.

    Parameters
    ----------
    leads:
        Qualified lead dictionaries.
    summary:
        Aggregated execution summary.

    Returns
    -------
    dict[str, str]
        Paths of generated local artifacts.
    """
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = EXPORT_DIR / "qualified_leads.csv"
    html_path = EXPORT_DIR / "qualified_leads.html"
    json_path = EXPORT_DIR / "qualified_leads.json"

    rows = _csv_rows(leads)
    _write_csv(csv_path, rows)
    _write_html(html_path, leads, summary)
    json_path.write_text(json.dumps(_sorted_leads(leads), ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "csv_path": str(csv_path),
        "html_path": str(html_path),
        "json_path": str(json_path),
    }
