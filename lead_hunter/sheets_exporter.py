"""Google Sheets export helpers."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Sequence

import gspread
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials

from . import config

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _hex_to_rgb_fraction(hex_color: str) -> dict[str, float]:
    """Convert a hex color into the Sheets API RGB format."""
    cleaned = hex_color.lstrip("#")
    return {
        "red": int(cleaned[0:2], 16) / 255,
        "green": int(cleaned[2:4], 16) / 255,
        "blue": int(cleaned[4:6], 16) / 255,
    }


def _authorize_gspread() -> gspread.Client:
    """Authorize gspread using either inline JSON or a service-account file."""
    if config.GOOGLE_SERVICE_ACCOUNT_JSON:
        info = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
        credentials = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        credentials = Credentials.from_service_account_file(config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return gspread.authorize(credentials)


def _worksheet_title() -> str:
    """Build the weekly worksheet title."""
    today = datetime.now()
    iso_calendar = today.isocalendar()
    return f"Leads {iso_calendar.week:02d}/{iso_calendar.year}"


def _phone_formula(phone: str) -> str:
    """Create a clickable WhatsApp formula for Google Sheets."""
    digits = "".join(char for char in (phone or "") if char.isdigit())
    if not digits:
        return ""
    return f'=HYPERLINK("https://wa.me/{digits}","{phone}")'


def _instagram_formula(username: str) -> str:
    """Create a clickable Instagram formula for Google Sheets."""
    handle = (username or "").strip().lstrip("@")
    if not handle:
        return ""
    return f'=HYPERLINK("https://www.instagram.com/{handle}/","@{handle}")'


def _score_sort_key(lead: dict[str, Any]) -> tuple[int, int]:
    """Sort HOT first, then WARM, both by descending score."""
    order = {"HOT": 0, "WARM": 1, "COLD": 2, "SKIP": 3}
    return (order.get(lead.get("status", "SKIP"), 99), -(int(lead.get("score") or 0)))


def _rows_from_leads(leads: Sequence[dict[str, Any]]) -> list[list[Any]]:
    """Convert lead dictionaries into sheet rows."""
    rows: list[list[Any]] = [config.SHEETS_HEADERS]
    for lead in sorted(leads, key=_score_sort_key):
        rows.append(
            [
                lead.get("status_display", ""),
                int(lead.get("score") or 0),
                lead.get("name", ""),
                lead.get("category", ""),
                lead.get("neighborhood", ""),
                lead.get("city", ""),
                _phone_formula(lead.get("phone", "")),
                _instagram_formula(lead.get("instagram_username", "")),
                lead.get("link_type_label", lead.get("link_type", "")),
                lead.get("followers_count") or "",
                round(float(lead.get("engagement_rate") or 0), 2),
                int(lead.get("google_reviews") or 0),
                round(float(lead.get("google_rating") or 0), 1),
                lead.get("last_post_days") if lead.get("last_post_days") is not None else "N/D",
                " | ".join(lead.get("key_strengths") or []),
                lead.get("whatsapp_message", ""),
                lead.get("instagram_dm", ""),
                lead.get("collected_at", ""),
                "",
                "",
            ]
        )
    return rows


def _format_sheet(
    spreadsheet: gspread.Spreadsheet,
    worksheet: gspread.Worksheet,
    hot_count: int,
    warm_count: int,
    total_rows: int,
) -> None:
    """Apply formatting and conditional rules to the worksheet."""
    sheet_id = worksheet.id
    requests: list[dict[str, Any]] = [
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {
                        "frozenRowCount": 1,
                        "frozenColumnCount": 1,
                    },
                },
                "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 20,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": _hex_to_rgb_fraction("#1F2937"),
                        "textFormat": {"bold": True, "foregroundColor": _hex_to_rgb_fraction("#FFFFFF")},
                        "horizontalAlignment": "CENTER",
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": max(total_rows, 2),
                    "startColumnIndex": 15,
                    "endColumnIndex": 17,
                },
                "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP"}},
                "fields": "userEnteredFormat.wrapStrategy",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 15,
                    "endIndex": 17,
                },
                "properties": {"pixelSize": 280},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": 15,
                },
                "properties": {"pixelSize": 140},
                "fields": "pixelSize",
            }
        },
    ]

    if hot_count:
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": 1 + hot_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": 20,
                    },
                    "cell": {"userEnteredFormat": {"backgroundColor": _hex_to_rgb_fraction("#FCE8E6")}},
                    "fields": "userEnteredFormat.backgroundColor",
                }
            }
        )

    if warm_count:
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1 + hot_count,
                        "endRowIndex": 1 + hot_count + warm_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": 20,
                    },
                    "cell": {"userEnteredFormat": {"backgroundColor": _hex_to_rgb_fraction("#FEF9E7")}},
                    "fields": "userEnteredFormat.backgroundColor",
                }
            }
        )

    requests.extend(
        [
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": max(total_rows, 2),
                                "startColumnIndex": 1,
                                "endColumnIndex": 2,
                            }
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "NUMBER_GREATER_THAN_EQ",
                                "values": [{"userEnteredValue": "75"}],
                            },
                            "format": {
                                "backgroundColor": _hex_to_rgb_fraction("#E74C3C"),
                                "textFormat": {
                                    "bold": True,
                                    "foregroundColor": _hex_to_rgb_fraction("#FFFFFF"),
                                },
                            },
                        },
                    },
                    "index": 0,
                }
            },
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": max(total_rows, 2),
                                "startColumnIndex": 1,
                                "endColumnIndex": 2,
                            }
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "NUMBER_BETWEEN",
                                "values": [
                                    {"userEnteredValue": "60"},
                                    {"userEnteredValue": "74"},
                                ],
                            },
                            "format": {
                                "backgroundColor": _hex_to_rgb_fraction("#F4D03F"),
                                "textFormat": {"bold": True},
                            },
                        },
                    },
                    "index": 1,
                }
            },
        ]
    )

    spreadsheet.batch_update({"requests": requests})


def export_leads(leads: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Export qualified leads to a formatted Google Sheet.

    Parameters
    ----------
    leads:
        Sequence of flattened lead dictionaries already filtered to HOT/WARM.

    Returns
    -------
    dict[str, Any]
        Worksheet metadata including direct URL and counts.
    """
    if not config.GOOGLE_SHEETS_ID:
        raise ValueError("GOOGLE_SHEETS_ID não configurado em config.py")

    client = _authorize_gspread()
    spreadsheet = client.open_by_key(config.GOOGLE_SHEETS_ID)
    worksheet_name = _worksheet_title()

    try:
        existing = spreadsheet.worksheet(worksheet_name)
        spreadsheet.del_worksheet(existing)
    except WorksheetNotFound:
        pass

    worksheet = spreadsheet.add_worksheet(
        title=worksheet_name,
        rows=max(len(leads) + 10, 100),
        cols=len(config.SHEETS_HEADERS),
    )

    rows = _rows_from_leads(leads)
    worksheet.update(rows, value_input_option="USER_ENTERED")

    hot_count = sum(1 for lead in leads if lead.get("status") == "HOT")
    warm_count = sum(1 for lead in leads if lead.get("status") == "WARM")
    _format_sheet(spreadsheet, worksheet, hot_count=hot_count, warm_count=warm_count, total_rows=len(rows))

    return {
        "worksheet_name": worksheet_name,
        "worksheet_id": worksheet.id,
        "sheet_url": f"https://docs.google.com/spreadsheets/d/{config.GOOGLE_SHEETS_ID}/edit#gid={worksheet.id}",
        "rows_written": len(rows) - 1,
        "hot_count": hot_count,
        "warm_count": warm_count,
    }
