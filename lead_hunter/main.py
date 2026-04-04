"""Main orchestration flow for the lead hunter pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import random
import time
from copy import deepcopy
from typing import Any

from . import config
from .email_notifier import send_notification
from .instagram_scraper import extract_instagram_from_text, get_instagram_data
from .link_detector import analyze_website
from .local_exporter import export_local_files
from .maps_scraper import get_places
from .message_writer import generate_message
from .scorer import calculate_score
from .sheets_exporter import export_leads

logger = logging.getLogger(__name__)

DEFAULT_CHECKPOINT = {
    "processed_place_ids": [],
    "qualified_leads": [],
    "errors": [],
    "apify_calls_used": 0,
    "stats": {
        "found": 0,
        "processed": 0,
        "qualified": 0,
        "hot": 0,
        "warm": 0,
        "errors": 0,
    },
}


def _setup_logging() -> None:
    """Configure console and file logging."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")

    file_handler = logging.FileHandler(config.LOG_FILE_PATH, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


def _load_checkpoint() -> dict[str, Any]:
    """Load checkpoint data from disk."""
    if not config.CHECKPOINT_PATH.exists():
        return deepcopy(DEFAULT_CHECKPOINT)
    with config.CHECKPOINT_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)
    merged = deepcopy(DEFAULT_CHECKPOINT)
    merged.update(data)
    merged["stats"] = {**DEFAULT_CHECKPOINT["stats"], **data.get("stats", {})}
    _refresh_stats(merged)
    return merged


def _refresh_stats(state: dict[str, Any]) -> None:
    """Recalculate derived counters from the qualified lead list."""
    qualified_leads = state.get("qualified_leads", [])
    state["stats"]["qualified"] = len(qualified_leads)
    state["stats"]["hot"] = sum(1 for lead in qualified_leads if lead.get("status") == "HOT")
    state["stats"]["warm"] = sum(1 for lead in qualified_leads if lead.get("status") == "WARM")


def _save_checkpoint(state: dict[str, Any]) -> None:
    """Persist checkpoint and latest qualified leads snapshot."""
    _refresh_stats(state)
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with config.CHECKPOINT_PATH.open("w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)
    with config.LEADS_SNAPSHOT_PATH.open("w", encoding="utf-8") as file:
        json.dump(state.get("qualified_leads", []), file, ensure_ascii=False, indent=2)


def _validate_required_config() -> None:
    """Validate required configuration before running."""
    required = {
        "GOOGLE_MAPS_API_KEY": config.GOOGLE_MAPS_API_KEY,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise ValueError(f"Configuração ausente: {', '.join(missing)}")


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Pipeline de geração de leads B2B para restaurantes.")
    parser.add_argument("--max-apify-calls", type=int, default=config.APIFY_MAX_CALLS_PER_SESSION)
    parser.add_argument("--skip-sheets", action="store_true")
    parser.add_argument("--skip-email", action="store_true")
    parser.add_argument("--limit-cities", type=int, default=0)
    parser.add_argument("--limit-categories", type=int, default=0)
    parser.add_argument("--cities", type=str, default="",
                        help="Cidades separadas por | (pipe). Vazio = todas.")
    parser.add_argument("--categories", type=str, default="",
                        help="Categorias separadas por | (pipe). Vazio = todas.")
    parser.add_argument("--fresh", action="store_true",
                        help="Inicia nova rodada zerando IDs processados (preserva leads qualificados).")
    return parser.parse_args()


def _record_error(state: dict[str, Any], place_data: dict[str, Any], stage: str, message: str) -> None:
    """Record one processing error without stopping the full run."""
    state["errors"].append(
        {
            "place_id": place_data.get("place_id", ""),
            "name": place_data.get("name", ""),
            "stage": stage,
            "message": message,
            "status": "erro_coleta",
            "collected_at": place_data.get("collected_at", ""),
        }
    )
    state["stats"]["errors"] += 1


def _gather_instagram_username(place_data: dict[str, Any], link_data: dict[str, Any]) -> str | None:
    """Extract the best Instagram username candidate from known sources."""
    review_text = " ".join(review.get("text", "") for review in (place_data.get("reviews") or []))
    candidates = [
        link_data.get("instagram_url", ""),
        place_data.get("website", ""),
        link_data.get("final_url", ""),
        place_data.get("editorial_summary", ""),
        review_text,
    ]
    for text in candidates:
        username = extract_instagram_from_text(text)
        if username:
            return username
    return None


def _link_type_label(link_type: str) -> str:
    """Map internal link types to user-facing labels."""
    mapping = {
        "sem_link": "Sem link",
        "whatsapp": "WhatsApp",
        "linktree": "Linktree",
        "bio_link": "Bio link",
        "ifood": "iFood",
        "delivery_app": "App de delivery",
        "social_profile": "Instagram/Facebook",
        "wix_basic": "Wix/site básico",
        "site_basico": "Site simples",
        "site_inacessivel": "Site inacessível",
        "site_real": "Site profissional",
    }
    return mapping.get(link_type, link_type or "N/D")


def _build_lead_record(
    place_data: dict[str, Any],
    link_data: dict[str, Any],
    ig_data: dict[str, Any],
    score_data: dict[str, Any],
    messages: dict[str, Any],
) -> dict[str, Any]:
    """Build the flattened lead record used by Sheets, email, and checkpoint."""
    status = score_data.get("classification", "SKIP")
    status_display = "HOT 🔥" if status == "HOT" else "WARM ✓"
    return {
        "place_id": place_data.get("place_id", ""),
        "status": status,
        "status_display": status_display,
        "score": score_data.get("total_score", 0),
        "name": place_data.get("name", ""),
        "category": place_data.get("category", ""),
        "neighborhood": place_data.get("neighborhood", ""),
        "city": place_data.get("city", ""),
        "phone": place_data.get("formatted_phone_number") or link_data.get("whatsapp_number", ""),
        "instagram_username": ig_data.get("username", ""),
        "link_type": link_data.get("link_type", ""),
        "link_type_label": _link_type_label(link_data.get("link_type", "")),
        "followers_count": ig_data.get("followers_count"),
        "engagement_rate": ig_data.get("engagement_rate"),
        "google_reviews": place_data.get("user_ratings_total"),
        "google_rating": place_data.get("rating"),
        "last_post_days": ig_data.get("days_since_last_post"),
        "key_strengths": score_data.get("key_strengths", []),
        "whatsapp_message": messages.get("whatsapp_message", ""),
        "whatsapp_followup": messages.get("whatsapp_followup", ""),
        "instagram_dm": messages.get("instagram_dm", ""),
        "subject_email": messages.get("subject_email", ""),
        "approach_angle": messages.get("approach_angle", ""),
        "collected_at": place_data.get("collected_at", ""),
        "maps_url": place_data.get("maps_url", ""),
        "website": place_data.get("website", ""),
        "score_breakdown": score_data.get("score_breakdown", {}),
        "place_data": place_data,
        "link_data": link_data,
        "instagram_data": ig_data,
    }


def _upsert_qualified_lead(state: dict[str, Any], lead_record: dict[str, Any]) -> None:
    """Insert or replace one qualified lead, tracking repeat encounters."""
    existing_index = next(
        (index for index, item in enumerate(state["qualified_leads"]) if item.get("place_id") == lead_record["place_id"]),
        None,
    )
    if existing_index is None:
        # First time this lead is found
        lead_record["first_seen_at"] = lead_record.get("collected_at", "")
        lead_record["run_count"] = 1
        lead_record["is_new"] = True
        state["qualified_leads"].append(lead_record)
    else:
        # Lead already known — preserve original discovery date, increment counter
        old = state["qualified_leads"][existing_index]
        lead_record["first_seen_at"] = old.get("first_seen_at") or old.get("collected_at", "")
        lead_record["run_count"] = old.get("run_count", 1) + 1
        lead_record["is_new"] = False
        state["qualified_leads"][existing_index] = lead_record


def _sleep_random_external() -> None:
    """Apply a small randomized delay between external requests."""
    time.sleep(random.uniform(*config.REQUEST_DELAY_RANGE_SECONDS))


def main() -> int:
    """Run the end-to-end lead generation pipeline."""
    _setup_logging()
    _validate_required_config()
    args = _parse_args()
    state = _load_checkpoint()

    if args.fresh:
        # New round: scan all cities/categories again, keep accumulated qualified leads
        processed_place_ids: set[str] = set()
        state["processed_place_ids"] = []
        state["apify_calls_used"] = 0
        state["stats"] = {**DEFAULT_CHECKPOINT["stats"],
                          "qualified": len(state.get("qualified_leads", [])),
                          "hot": sum(1 for l in state.get("qualified_leads", []) if l.get("status") == "HOT"),
                          "warm": sum(1 for l in state.get("qualified_leads", []) if l.get("status") == "WARM")}
        logger.info("[FRESH] Nova rodada iniciada — %d leads acumulados preservados.",
                    len(state.get("qualified_leads", [])))
    else:
        processed_place_ids = set(state.get("processed_place_ids", []))
    apify_calls_used = int(state.get("apify_calls_used", 0))
    processed_since_checkpoint = 0

    if args.cities:
        cities = [c.strip() for c in args.cities.split("|") if c.strip()]
    else:
        cities = config.TARGET_CITIES[: args.limit_cities or None]

    if args.categories:
        categories = [c.strip() for c in args.categories.split("|") if c.strip()]
    else:
        categories = config.TARGET_CATEGORIES[: args.limit_categories or None]

    total_combos = max(len(cities) * len(categories), 1)
    combo_done = 0

    logger.info("Iniciando pipeline com %s cidades x %s categorias", len(cities), len(categories))

    for city in cities:
        for category in categories:
            combo_done += 1
            pct = int(combo_done / total_combos * 100)
            logger.info("[PROGRESS] %d/%d (%d%%) — %s × %s", combo_done, total_combos, pct, city, category)
            try:
                places = get_places(city, category, seen_place_ids=processed_place_ids)
                state["stats"]["found"] += len(places)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Falha ao coletar Maps em %s / %s: %s", city, category, exc)
                continue

            for place_data in places:
                place_id = place_data.get("place_id")
                if not place_id or place_id in processed_place_ids:
                    continue

                logger.info("Processando %s (%s)", place_data.get("name", "Sem nome"), city)
                try:
                    link_data = analyze_website(place_data.get("website"))
                    instagram_username = _gather_instagram_username(place_data, link_data)
                    prefer_apify = bool(
                        instagram_username and config.APIFY_TOKEN and apify_calls_used < args.max_apify_calls
                    )
                    ig_data = get_instagram_data(instagram_username, prefer_apify=prefer_apify)
                    if ig_data.get("used_apify"):
                        apify_calls_used += 1

                    score_input_place = dict(place_data)
                    score_input_place["current_link_type"] = link_data.get("link_type", "")
                    score_data = calculate_score(score_input_place, link_data, ig_data)

                    if ig_data.get("collection_status") == "error_coleta":
                        _record_error(state, place_data, "instagram", ig_data.get("error", "erro_coleta"))

                    if score_data["classification"] in {"HOT", "WARM"} and not score_data["disqualified"]:
                        time.sleep(config.GEMINI_DELAY_SECONDS)
                        messages = generate_message(score_input_place, ig_data, score_data)
                        lead_record = _build_lead_record(score_input_place, link_data, ig_data, score_data, messages)
                        _upsert_qualified_lead(state, lead_record)
                        _refresh_stats(state)
                    else:
                        logger.info(
                            "Lead descartado: %s (%s)",
                            place_data.get("name", ""),
                            score_data.get("classification", "SKIP"),
                        )

                except Exception as exc:  # noqa: BLE001
                    logger.exception("Falha ao processar lead %s: %s", place_data.get("name", ""), exc)
                    _record_error(state, place_data, "pipeline", str(exc))
                finally:
                    processed_place_ids.add(place_id)
                    state["processed_place_ids"] = sorted(processed_place_ids)
                    state["apify_calls_used"] = apify_calls_used
                    state["stats"]["processed"] += 1
                    processed_since_checkpoint += 1
                    if processed_since_checkpoint >= config.CHECKPOINT_EVERY:
                        _save_checkpoint(state)
                        processed_since_checkpoint = 0
                    _sleep_random_external()

    _save_checkpoint(state)

    qualified_leads = sorted(state["qualified_leads"], key=lambda lead: (lead["status"] != "HOT", -lead["score"]))
    local_exports = export_local_files(qualified_leads, state["stats"])
    sheet_result: dict[str, Any] = {}
    if qualified_leads and not args.skip_sheets and config.GOOGLE_SHEETS_ID:
        try:
            sheet_result = export_leads(qualified_leads)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Falha ao exportar para Sheets: %s", exc)
            _record_error(state, {"name": "Google Sheets"}, "sheets", str(exc))
            _save_checkpoint(state)

    if not args.skip_email:
        try:
            send_notification(
                summary=state["stats"],
                qualified_leads=qualified_leads,
                sheet_url=sheet_result.get("sheet_url", ""),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Falha ao enviar e-mail de notificação: %s", exc)
            _record_error(state, {"name": "Email"}, "email", str(exc))
            _save_checkpoint(state)

    logger.info(
        "Resumo final | encontrados=%s processados=%s qualificados=%s HOT=%s WARM=%s erros=%s | csv=%s | html=%s",
        state["stats"]["found"],
        state["stats"]["processed"],
        len(qualified_leads),
        sum(1 for lead in qualified_leads if lead.get("status") == "HOT"),
        sum(1 for lead in qualified_leads if lead.get("status") == "WARM"),
        state["stats"]["errors"],
        local_exports.get("csv_path", ""),
        local_exports.get("html_path", ""),
    )
    logger.info("[COMPLETE] Pipeline concluído.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
