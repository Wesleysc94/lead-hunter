"""Notification email sender."""

from __future__ import annotations

import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Sequence

from . import config


def _build_top_rows(leads: Sequence[dict[str, Any]]) -> str:
    """Render the HTML rows for the top HOT leads."""
    top_hot = [lead for lead in leads if lead.get("status") == "HOT"][:5]
    rows = []
    for lead in top_hot:
        rows.append(
            f"""
            <tr>
              <td style="padding:8px;border:1px solid #ddd;">{lead.get("name", "")}</td>
              <td style="padding:8px;border:1px solid #ddd;">{lead.get("neighborhood", "")}</td>
              <td style="padding:8px;border:1px solid #ddd;">{lead.get("score", "")}</td>
              <td style="padding:8px;border:1px solid #ddd;">{lead.get("followers_count", "")}</td>
            </tr>
            """.strip()
        )
    return "\n".join(rows)


def send_notification(summary: dict[str, Any], qualified_leads: Sequence[dict[str, Any]], sheet_url: str = "") -> bool:
    """Send an HTML notification email with weekly lead summary.

    Parameters
    ----------
    summary:
        Aggregated execution summary.
    qualified_leads:
        Qualified HOT/WARM leads saved this run.
    sheet_url:
        Direct URL to the Google Sheet tab, when available.

    Returns
    -------
    bool
        ``True`` when the email was sent, otherwise ``False``.
    """
    if not (config.NOTIFICATION_EMAIL and config.SMTP_EMAIL and config.SMTP_APP_PASSWORD):
        return False

    message = MIMEMultipart("alternative")
    message["Subject"] = f"🔥 {summary.get('qualified', 0)} leads qualificados esta semana"
    message["From"] = config.SMTP_EMAIL
    message["To"] = config.NOTIFICATION_EMAIL

    link_block = (
        f'<p><a href="{sheet_url}" target="_blank">Abrir planilha de leads</a></p>' if sheet_url else ""
    )
    html_body = f"""
    <html>
      <body style="font-family:Arial,sans-serif;color:#222;">
        <h2>Resumo da rodada de prospecção</h2>
        <p><strong>Encontrados:</strong> {summary.get("found", 0)}<br>
           <strong>Qualificados:</strong> {summary.get("qualified", 0)}<br>
           <strong>HOTs:</strong> {summary.get("hot", 0)}</p>
        <h3>Top 5 HOTs</h3>
        <table style="border-collapse:collapse;">
          <thead>
            <tr>
              <th style="padding:8px;border:1px solid #ddd;background:#f3f4f6;">Nome</th>
              <th style="padding:8px;border:1px solid #ddd;background:#f3f4f6;">Bairro</th>
              <th style="padding:8px;border:1px solid #ddd;background:#f3f4f6;">Score</th>
              <th style="padding:8px;border:1px solid #ddd;background:#f3f4f6;">Seguidores</th>
            </tr>
          </thead>
          <tbody>
            {_build_top_rows(qualified_leads)}
          </tbody>
        </table>
        {link_block}
        <p>Coleta finalizada em {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}.</p>
      </body>
    </html>
    """.strip()
    message.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(config.SMTP_EMAIL, config.SMTP_APP_PASSWORD)
        smtp.sendmail(config.SMTP_EMAIL, [config.NOTIFICATION_EMAIL], message.as_string())
    return True

