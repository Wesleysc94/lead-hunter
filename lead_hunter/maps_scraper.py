"""Google Maps / Places collection helpers."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Iterable

import requests

from . import config

logger = logging.getLogger(__name__)


def _build_headers(field_mask: str) -> dict[str, str]:
    """Build default Google Places headers."""
    return {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": config.GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": field_mask,
        "User-Agent": config.USER_AGENT,
    }


def _extract_neighborhood(formatted_address: str | None) -> str:
    """Try to infer the neighborhood from a Brazilian formatted address."""
    if not formatted_address:
        return ""

    parts = [part.strip() for part in formatted_address.split(" - ") if part.strip()]
    if len(parts) >= 2:
        candidate = parts[1]
        if "," in candidate:
            candidate = candidate.split(",")[0].strip()
        return candidate

    segments = [segment.strip() for segment in formatted_address.split(",") if segment.strip()]
    if len(segments) >= 2:
        return segments[-2]
    return ""


def _normalize_reviews(reviews: list[dict] | None) -> list[dict]:
    """Normalize Google reviews to a compact schema."""
    normalized: list[dict] = []
    for review in reviews or []:
        normalized.append(
            {
                "author_name": review.get("authorAttribution", {}).get("displayName", ""),
                "rating": review.get("rating"),
                "text": review.get("text", {}).get("text", ""),
                "relative_time_description": review.get("relativePublishTimeDescription", ""),
                "timestamp": review.get("publishTime", ""),
            }
        )
    return normalized[:3]


def _is_permanently_closed(place_details: dict) -> bool:
    """Return True when the business is permanently closed or moved."""
    return place_details.get("businessStatus") == "CLOSED_PERMANENTLY"


def _passes_minimum_filters(place_details: dict) -> bool:
    """Apply the minimum collection filters required by the business rules."""
    rating = float(place_details.get("rating") or 0)
    ratings_total = int(place_details.get("userRatingCount") or 0)
    return rating >= 4.0 and ratings_total >= 30 and not _is_permanently_closed(place_details)


def _normalize_place(search_place: dict, details_place: dict, city: str, category: str) -> dict:
    """Merge search and detail payloads into the project schema."""
    display_name = details_place.get("displayName", {}).get("text") or search_place.get(
        "displayName", {}
    ).get("text", "")
    formatted_address = details_place.get("formattedAddress") or search_place.get("formattedAddress", "")
    national_phone = details_place.get("nationalPhoneNumber")
    international_phone = details_place.get("internationalPhoneNumber")
    primary_type = details_place.get("primaryTypeDisplayName", {}).get("text") or search_place.get(
        "primaryTypeDisplayName", {}
    ).get("text", "")
    regular_opening = details_place.get("regularOpeningHours") or details_place.get("currentOpeningHours") or {}
    editorial_summary = details_place.get("editorialSummary", {}).get("text", "")

    return {
        "place_id": details_place.get("id") or search_place.get("id"),
        "name": display_name,
        "formatted_address": formatted_address,
        "neighborhood": _extract_neighborhood(formatted_address),
        "formatted_phone_number": national_phone or international_phone or "",
        "international_phone_number": international_phone or "",
        "website": details_place.get("websiteUri") or "",
        "rating": float(details_place.get("rating") or 0),
        "user_ratings_total": int(details_place.get("userRatingCount") or 0),
        "opening_hours": regular_opening,
        "price_level": details_place.get("priceLevel", ""),
        "editorial_summary": editorial_summary,
        "reviews": _normalize_reviews(details_place.get("reviews")),
        "business_status": details_place.get("businessStatus", ""),
        "maps_url": details_place.get("googleMapsUri", ""),
        "primary_type": details_place.get("primaryType", ""),
        "primary_type_display_name": primary_type,
        "city": city,
        "category": category,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


def get_place_details(place_id: str, session: requests.Session | None = None) -> dict:
    """Fetch detailed information for a single place ID.

    Parameters
    ----------
    place_id:
        Google place identifier returned by Places Text Search.
    session:
        Optional requests session for connection reuse.

    Returns
    -------
    dict
        Normalized details payload from Place Details (New), or an empty dict on
        failure.
    """
    if not config.GOOGLE_MAPS_API_KEY:
        raise ValueError("GOOGLE_MAPS_API_KEY não configurada em config.py")

    close_session = session is None
    active_session = session or requests.Session()
    try:
        url = config.MAPS_PLACE_DETAILS_URL.format(place_id=place_id)
        response = active_session.get(
            url,
            headers=_build_headers(config.MAPS_PLACE_DETAILS_FIELDS),
            params={"languageCode": "pt-BR", "regionCode": "BR"},
            timeout=20,
        )
        time.sleep(config.MAPS_REQUEST_DELAY_SECONDS)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        logger.exception("Falha ao buscar detalhes do place_id %s: %s", place_id, exc)
        return {}
    finally:
        if close_session:
            active_session.close()


def get_places(city: str, category: str, seen_place_ids: Iterable[str] | None = None) -> list[dict]:
    """Collect Google Maps leads for a city/category pair.

    Parameters
    ----------
    city:
        Search city or neighborhood string.
    category:
        Search category string.
    seen_place_ids:
        Optional iterable of already processed place IDs to skip.

    Returns
    -------
    list[dict]
        List of normalized place dictionaries with details, deduplicated by
        place_id, already filtered by rating, review count, and closure status.
    """
    if not config.GOOGLE_MAPS_API_KEY:
        raise ValueError("GOOGLE_MAPS_API_KEY não configurada em config.py")

    seen = set(seen_place_ids or [])
    collected: dict[str, dict] = {}
    query = f"{category} em {city}"

    with requests.Session() as session:
        next_page_token = ""
        for page_index in range(config.MAX_GOOGLE_MAPS_PAGES):
            payload = {
                "textQuery": query,
                "languageCode": "pt-BR",
                "regionCode": "BR",
                "pageSize": config.GOOGLE_MAPS_PAGE_SIZE,
                "strictTypeFiltering": False,
            }
            if next_page_token:
                payload["pageToken"] = next_page_token
                time.sleep(config.MAPS_PAGE_DELAY_SECONDS)

            try:
                response = session.post(
                    config.MAPS_TEXT_SEARCH_URL,
                    headers=_build_headers(config.MAPS_TEXT_SEARCH_FIELDS),
                    json=payload,
                    timeout=20,
                )
                time.sleep(config.MAPS_REQUEST_DELAY_SECONDS)
                response.raise_for_status()
                body = response.json()
            except requests.RequestException as exc:
                logger.exception(
                    "Falha no Text Search para cidade=%s categoria=%s página=%s: %s",
                    city,
                    category,
                    page_index + 1,
                    exc,
                )
                break

            for search_place in body.get("places", []):
                place_id = search_place.get("id")
                if not place_id or place_id in seen or place_id in collected:
                    continue

                details = get_place_details(place_id, session=session)
                if not details:
                    continue

                if _passes_minimum_filters(details):
                    collected[place_id] = _normalize_place(search_place, details, city, category)

            next_page_token = body.get("nextPageToken", "")
            if not next_page_token:
                break

    logger.info(
        "Maps coletou %s lugares válidos para '%s' em '%s'",
        len(collected),
        category,
        city,
    )
    return list(collected.values())

