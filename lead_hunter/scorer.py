"""Lead scoring logic."""

from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from typing import Any

from . import config


def _normalize_text(value: str | None) -> str:
    """Normalize text for case-insensitive and accent-insensitive checks."""
    text = (value or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _contains_any(text: str, keywords: list[str]) -> bool:
    """Return True if any normalized keyword appears in text."""
    normalized_text = _normalize_text(text)
    return any(_normalize_text(keyword) in normalized_text for keyword in keywords)


def _estimate_years_active_bonus(place_data: dict[str, Any]) -> int:
    """Estimate whether the business appears to be active for at least two years."""
    reviews = place_data.get("reviews") or []
    timestamps: list[datetime] = []
    for review in reviews:
        timestamp = review.get("timestamp")
        if not timestamp:
            continue
        try:
            timestamps.append(datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")))
        except ValueError:
            continue

    if timestamps:
        oldest = min(timestamps)
        if (datetime.now(timezone.utc) - oldest).days >= 730:
            return 2
    return 0


def _is_chain_or_franchise(name: str) -> bool:
    """Return True when the brand name looks like a franchise chain."""
    normalized_name = _normalize_text(name)
    return any(chain in normalized_name for chain in (_normalize_text(item) for item in config.CHAIN_KEYWORDS))


def _has_premium_neighborhood(place_data: dict[str, Any]) -> bool:
    """Return True when the address matches a premium neighborhood."""
    haystack = " ".join(
        [
            place_data.get("neighborhood", ""),
            place_data.get("formatted_address", ""),
            place_data.get("city", ""),
        ]
    )
    return _contains_any(haystack, config.PREMIUM_NEIGHBORHOODS)


def _has_premium_branding(place_data: dict[str, Any], ig_data: dict[str, Any]) -> bool:
    """Return True when the business names or categories signal premium positioning."""
    haystack = " ".join(
        [
            place_data.get("name", ""),
            place_data.get("category", ""),
            place_data.get("primary_type_display_name", ""),
            ig_data.get("category", ""),
            " ".join(ig_data.get("recent_captions") or []),
        ]
    )
    return _contains_any(haystack, config.PREMIUM_KEYWORDS)


def _has_restaurant_business_category(ig_data: dict[str, Any]) -> bool:
    """Return True when the IG category confirms restaurant intent."""
    return _contains_any(ig_data.get("category", ""), config.RESTAURANT_CATEGORY_KEYWORDS)


def _qualify_link_problem(link_data: dict[str, Any]) -> tuple[int, str]:
    """Map link type to problem severity points and label."""
    link_type = link_data.get("link_type", "")
    if link_data.get("has_professional_site") or link_type == "site_real":
        return -35, "Tem site profissional próprio com cardápio"
    if link_type in {"sem_link", "whatsapp"}:
        return 35, "Depende de WhatsApp/sem site próprio"
    if link_type in {"linktree", "bio_link", "social_profile"}:
        return 30, "Usa bio link/social como principal presença web"
    if link_type in {"ifood", "delivery_app"}:
        return 25, "Usa app de delivery como 'site'"
    if link_type in {"wix_basic", "site_basico", "site_inacessivel"}:
        return 15, "Tem site básico/amador sem estrutura forte"
    return 0, ""


def calculate_score(place_data: dict[str, Any], link_data: dict[str, Any], ig_data: dict[str, Any]) -> dict[str, Any]:
    """Calculate the lead quality score and qualification details.

    Parameters
    ----------
    place_data:
        Normalized Google Maps data for the restaurant.
    link_data:
        Website analysis output from ``analyze_website``.
    ig_data:
        Instagram metrics from ``get_instagram_data``.

    Returns
    -------
    dict[str, Any]
        Total score, classification, breakdown, disqualification flags, and key
        strengths for outreach messaging.
    """
    score_breakdown = {
        "problem_clarity": 0,
        "business_health": 0,
        "digital_presence": 0,
        "conversion_potential": 0,
        "quality_bonus": 0,
    }
    strengths: list[tuple[int, str]] = []

    if link_data.get("has_professional_site") or link_data.get("link_type") == "site_real":
        return {
            "total_score": -1,
            "classification": "SKIP",
            "score_breakdown": score_breakdown,
            "disqualified": True,
            "disqualify_reason": "Tem site profissional com cardápio próprio",
            "key_strengths": [],
        }

    if _is_chain_or_franchise(place_data.get("name", "")):
        return {
            "total_score": -1,
            "classification": "SKIP",
            "score_breakdown": score_breakdown,
            "disqualified": True,
            "disqualify_reason": "Parece franquia/rede com baixa aderência ao ICP",
            "key_strengths": [],
        }

    if int(place_data.get("user_ratings_total") or 0) < 30:
        return {
            "total_score": -1,
            "classification": "SKIP",
            "score_breakdown": score_breakdown,
            "disqualified": True,
            "disqualify_reason": "Menos de 30 avaliações no Google",
            "key_strengths": [],
        }

    followers_count = ig_data.get("followers_count")
    if followers_count is not None and int(followers_count) < 100:
        return {
            "total_score": -1,
            "classification": "SKIP",
            "score_breakdown": score_breakdown,
            "disqualified": True,
            "disqualify_reason": "Menos de 100 seguidores no Instagram",
            "key_strengths": [],
        }

    last_post_days = ig_data.get("days_since_last_post")
    if last_post_days is not None and last_post_days > 60:
        return {
            "total_score": -1,
            "classification": "SKIP",
            "score_breakdown": score_breakdown,
            "disqualified": True,
            "disqualify_reason": "Conta do Instagram parece abandonada há mais de 60 dias",
            "key_strengths": [],
        }

    problem_points, problem_label = _qualify_link_problem(link_data)
    if problem_points < 0:
        return {
            "total_score": -1,
            "classification": "SKIP",
            "score_breakdown": score_breakdown,
            "disqualified": True,
            "disqualify_reason": problem_label,
            "key_strengths": [],
        }
    score_breakdown["problem_clarity"] = min(problem_points, 35)
    if problem_label:
        strengths.append((problem_points, problem_label))

    business_points = 0
    reviews_total = int(place_data.get("user_ratings_total") or 0)
    rating = float(place_data.get("rating") or 0)
    if reviews_total >= 200:
        business_points += 10
        strengths.append((10, f"{reviews_total} avaliações no Google"))
    if reviews_total >= 500:
        business_points += 5
    if reviews_total >= 1000:
        business_points += 5
    if rating >= 4.5:
        business_points += 5
        strengths.append((5, f"Rating forte ({rating:.1f})"))
    elif rating >= 4.2:
        business_points += 3
    business_points += _estimate_years_active_bonus(place_data)
    score_breakdown["business_health"] = min(business_points, 25)

    digital_points = 0
    engagement_rate = float(ig_data.get("engagement_rate") or 0)
    if followers_count is not None and int(followers_count) >= 1000:
        digital_points += 10
        strengths.append((10, f"Base de {int(followers_count)} seguidores"))
    if followers_count is not None and int(followers_count) >= 5000:
        digital_points += 5
    if last_post_days is not None and last_post_days <= 7:
        digital_points += 8
        strengths.append((8, "Perfil publicou na última semana"))
    elif last_post_days is not None and last_post_days <= 15:
        digital_points += 5
    if engagement_rate > 2:
        digital_points += 5
        strengths.append((5, f"Engajamento acima de 2% ({engagement_rate:.2f}%)"))
    if ig_data.get("is_business_account"):
        digital_points += 3

    digital_penalty = 0
    if last_post_days is not None and last_post_days > 30:
        digital_penalty -= 10
    score_breakdown["digital_presence"] = min(digital_points, 25) + digital_penalty

    conversion_points = 0
    if _has_premium_neighborhood(place_data):
        conversion_points += 5
        strengths.append((5, f"Bairro premium: {place_data.get('neighborhood') or place_data.get('city')}"))
    if _has_premium_branding(place_data, ig_data):
        conversion_points += 5
    if ig_data.get("has_visual_menu"):
        conversion_points += 3
    if _has_restaurant_business_category(ig_data):
        conversion_points += 2
    score_breakdown["conversion_potential"] = min(conversion_points, 15)

    quality_bonus = 0
    if link_data.get("whatsapp_number") or place_data.get("formatted_phone_number"):
        quality_bonus += 3
    if ig_data.get("captions_show_care"):
        quality_bonus += 2
    score_breakdown["quality_bonus"] = min(quality_bonus, 5)

    total_score = sum(score_breakdown.values())
    if total_score >= 75:
        classification = "HOT"
    elif total_score >= 60:
        classification = "WARM"
    elif total_score >= 40:
        classification = "COLD"
    else:
        classification = "SKIP"

    sorted_strengths = [
        label for _, label in sorted(strengths, key=lambda item: item[0], reverse=True) if label
    ]
    deduped_strengths: list[str] = []
    for label in sorted_strengths:
        if label not in deduped_strengths:
            deduped_strengths.append(label)
        if len(deduped_strengths) == 3:
            break

    return {
        "total_score": int(round(total_score)),
        "classification": classification,
        "score_breakdown": score_breakdown,
        "disqualified": False,
        "disqualify_reason": "",
        "key_strengths": deduped_strengths,
    }

