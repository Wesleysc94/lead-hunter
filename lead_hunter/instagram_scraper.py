"""Instagram collection helpers using Apify with direct scraping fallback."""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from . import config

try:
    from apify_client import ApifyClient
except Exception:  # noqa: BLE001
    ApifyClient = None

logger = logging.getLogger(__name__)

INSTAGRAM_URL_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?instagram\.com/([A-Za-z0-9._]{1,30})/?",
    re.IGNORECASE,
)
INSTAGRAM_HANDLE_REGEX = re.compile(r"(?<![\w.])@([A-Za-z0-9._]{2,30})")
INSTAGRAM_RESERVED_HANDLES = {
    "p",
    "reel",
    "reels",
    "stories",
    "explore",
    "accounts",
    "direct",
    "developer",
    "privacy",
}


def extract_instagram_from_text(text: str | None) -> str | None:
    """Extract an Instagram username from free text, @handles, or URLs.

    Parameters
    ----------
    text:
        Any text blob that may contain an Instagram handle or URL.

    Returns
    -------
    str | None
        The normalized username if found, otherwise ``None``.
    """
    if not text:
        return None

    url_match = INSTAGRAM_URL_REGEX.search(text)
    if url_match:
        username = url_match.group(1).strip(" /")
        if username and username.lower() not in INSTAGRAM_RESERVED_HANDLES:
            return username

    for handle_match in INSTAGRAM_HANDLE_REGEX.finditer(text):
        username = handle_match.group(1).strip(" /")
        if username and username.lower() not in INSTAGRAM_RESERVED_HANDLES:
            return username
    return None


def _empty_instagram_data(username: str | None = None) -> dict[str, Any]:
    """Create the default Instagram payload."""
    profile_url = f"https://www.instagram.com/{username}/" if username else ""
    return {
        "username": username or "",
        "profile_url": profile_url,
        "followers_count": None,
        "following_count": None,
        "posts_count": None,
        "biography": "",
        "external_url": "",
        "is_business_account": False,
        "category": "",
        "latest_posts": [],
        "latest_post_timestamp": "",
        "days_since_last_post": None,
        "avg_likes": 0.0,
        "avg_comments": 0.0,
        "engagement_rate": 0.0,
        "premium_caption_hits": 0,
        "captions_show_care": False,
        "has_visual_menu": False,
        "bio_link_type": "",
        "collection_status": "missing_username" if not username else "not_collected",
        "source": "",
        "used_apify": False,
        "error": "",
        "recent_captions": [],
    }


def _classify_external_url(url: str | None) -> str:
    """Classify the external URL on the Instagram bio."""
    if not url:
        return ""
    lowered = url.lower()
    if any(domain in lowered for domain in config.WHATSAPP_DOMAINS):
        return "whatsapp"
    if any(domain in lowered for domain in config.BIO_LINK_DOMAINS):
        if "linktr.ee" in lowered:
            return "linktree"
        return "bio_link"
    if any(domain in lowered for domain in config.DELIVERY_DOMAINS):
        return "ifood" if "ifood.com.br" in lowered else "delivery_app"
    if any(domain in lowered for domain in config.SOCIAL_DOMAINS):
        return "social_profile"
    return "site"


def _parse_iso_datetime(value: str | int | float | None) -> datetime | None:
    """Parse timestamps from ISO strings or Unix epoch values."""
    if value in (None, ""):
        return None

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OSError, ValueError):
            return None

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.isdigit():
            return datetime.fromtimestamp(float(text), tz=timezone.utc)
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _caption_has_premium_terms(caption: str) -> bool:
    """Return True when the caption uses premium positioning vocabulary."""
    lowered = caption.lower()
    return any(keyword in lowered for keyword in config.PREMIUM_KEYWORDS)


def _caption_shows_care(caption: str) -> bool:
    """Heuristic for captions that show copywriting care."""
    if len(caption.strip()) < 35:
        return False
    punctuation_hits = sum(caption.count(mark) for mark in [".", "!", "?", ":", ";"])
    return punctuation_hits >= 1 or len(caption.split()) >= 8


def _caption_has_visual_menu(caption: str) -> bool:
    """Heuristic for product/menu-oriented captions."""
    lowered = caption.lower()
    return any(keyword in lowered for keyword in config.VISUAL_MENU_KEYWORDS)


def _normalize_post(post: dict[str, Any]) -> dict[str, Any]:
    """Normalize one post item from Apify or public Instagram endpoints."""
    caption = (post.get("caption") or "")[:200]
    likes_count = int(post.get("likesCount") or post.get("like_count") or post.get("likes_count") or 0)
    comments_count = int(
        post.get("commentsCount") or post.get("comment_count") or post.get("comments_count") or 0
    )
    timestamp = (
        post.get("timestamp")
        or post.get("takenAtTimestamp")
        or post.get("taken_at")
        or post.get("taken_at_timestamp")
        or ""
    )
    post_type = str(post.get("type") or post.get("media_type") or "photo").lower()
    if "sidecar" in post_type:
        post_type = "carousel"
    elif "video" in post_type and "reel" not in post_type:
        post_type = "video"
    elif "reel" in post_type:
        post_type = "reel"
    else:
        post_type = "photo"

    return {
        "timestamp": timestamp,
        "likes_count": likes_count,
        "comments_count": comments_count,
        "caption": caption,
        "type": post_type,
    }


def _finalize_instagram_data(base: dict[str, Any]) -> dict[str, Any]:
    """Compute derived Instagram metrics after raw data collection."""
    latest_posts = [_normalize_post(post) for post in (base.get("latest_posts") or [])[:12]]
    followers_count = base.get("followers_count") or 0
    likes = [post["likes_count"] for post in latest_posts]
    comments = [post["comments_count"] for post in latest_posts]
    post_dates = [
        dt for dt in (_parse_iso_datetime(post.get("timestamp")) for post in latest_posts) if dt is not None
    ]

    avg_likes = sum(likes) / len(likes) if likes else 0.0
    avg_comments = sum(comments) / len(comments) if comments else 0.0
    engagement_rate = 0.0
    if followers_count and latest_posts:
        engagement_rate = ((avg_likes + avg_comments) / followers_count) * 100

    latest_post_timestamp = max(post_dates).isoformat() if post_dates else ""
    days_since_last_post = None
    if post_dates:
        days_since_last_post = (datetime.now(timezone.utc) - max(post_dates)).days

    premium_caption_hits = sum(1 for post in latest_posts if _caption_has_premium_terms(post["caption"]))
    captions_show_care = sum(1 for post in latest_posts if _caption_shows_care(post["caption"])) >= max(
        1, math.ceil(len(latest_posts) / 3)
    )
    has_visual_menu = sum(1 for post in latest_posts if _caption_has_visual_menu(post["caption"])) >= 2

    base.update(
        {
            "latest_posts": latest_posts,
            "latest_post_timestamp": latest_post_timestamp,
            "days_since_last_post": days_since_last_post,
            "avg_likes": round(avg_likes, 2),
            "avg_comments": round(avg_comments, 2),
            "engagement_rate": round(engagement_rate, 2),
            "premium_caption_hits": premium_caption_hits,
            "captions_show_care": captions_show_care,
            "has_visual_menu": has_visual_menu,
            "bio_link_type": _classify_external_url(base.get("external_url")),
            "recent_captions": [post["caption"] for post in latest_posts[:3] if post["caption"]],
        }
    )
    return base


def _parse_apify_result(item: dict[str, Any], username: str) -> dict[str, Any]:
    """Convert Apify output into the internal schema."""
    data = _empty_instagram_data(username)
    data.update(
        {
            "username": item.get("username") or username,
            "profile_url": item.get("url") or data["profile_url"],
            "followers_count": item.get("followersCount"),
            "following_count": item.get("followsCount"),
            "posts_count": item.get("postsCount"),
            "biography": item.get("biography") or "",
            "external_url": item.get("externalUrl") or "",
            "is_business_account": bool(item.get("isBusinessAccount")),
            "category": item.get("businessCategoryName") or "",
            "latest_posts": item.get("latestPosts") or [],
            "collection_status": "ok",
            "source": "apify",
            "used_apify": True,
            "error": "",
        }
    )
    return _finalize_instagram_data(data)


def _fetch_instagram_via_apify(username: str) -> dict[str, Any]:
    """Fetch one Instagram profile through the Apify actor."""
    if not config.APIFY_TOKEN or ApifyClient is None:
        raise RuntimeError("Apify não configurado")

    client = ApifyClient(config.APIFY_TOKEN)
    actor = client.actor("apify/instagram-profile-scraper")
    input_variants = [
        {"usernames": [username], "resultsType": "details", "resultsLimit": 1},
        {"directUrls": [f"https://www.instagram.com/{username}/"], "resultsType": "details", "resultsLimit": 1},
    ]

    last_error: Exception | None = None
    for payload in input_variants:
        try:
            run = actor.call(run_input=payload, wait_secs=120)
            dataset_items = client.dataset(run["defaultDatasetId"]).list_items(limit=1).items
            if dataset_items:
                return _parse_apify_result(dataset_items[0], username)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("Apify falhou para @%s com payload %s: %s", username, payload, exc)

    raise RuntimeError(f"Apify sem retorno útil para @{username}: {last_error}")


def _extract_profile_from_public_api(payload: dict[str, Any], username: str) -> dict[str, Any]:
    """Parse the public Instagram web profile endpoint."""
    user = payload.get("data", {}).get("user") or payload.get("user") or {}
    if not user:
        raise ValueError("Resposta pública do Instagram sem objeto de usuário")

    latest_posts = []
    edges = (
        user.get("edge_owner_to_timeline_media", {}).get("edges")
        or user.get("timeline_media", {}).get("edges")
        or []
    )
    for edge in edges[:12]:
        node = edge.get("node", {})
        caption_edges = node.get("edge_media_to_caption", {}).get("edges", [])
        caption = caption_edges[0].get("node", {}).get("text", "") if caption_edges else ""
        latest_posts.append(
            {
                "timestamp": node.get("taken_at_timestamp"),
                "likes_count": node.get("edge_liked_by", {}).get("count")
                or node.get("edge_media_preview_like", {}).get("count")
                or 0,
                "comments_count": node.get("edge_media_to_comment", {}).get("count") or 0,
                "caption": caption,
                "type": "reel" if node.get("is_video") else "photo",
            }
        )

    data = _empty_instagram_data(username)
    data.update(
        {
            "username": user.get("username") or username,
            "profile_url": f"https://www.instagram.com/{user.get('username') or username}/",
            "followers_count": user.get("edge_followed_by", {}).get("count")
            or user.get("followers_count")
            or 0,
            "following_count": user.get("edge_follow", {}).get("count") or user.get("follows_count") or 0,
            "posts_count": user.get("edge_owner_to_timeline_media", {}).get("count")
            or user.get("media_count")
            or 0,
            "biography": user.get("biography") or "",
            "external_url": user.get("external_url") or "",
            "is_business_account": bool(
                user.get("is_business_account")
                or user.get("is_business")
                or user.get("business_address_json")
            ),
            "category": user.get("category_name") or user.get("business_category_name") or "",
            "latest_posts": latest_posts,
            "collection_status": "ok",
            "source": "instagram_public_api",
            "used_apify": False,
            "error": "",
        }
    )
    return _finalize_instagram_data(data)


def _fetch_instagram_public(username: str) -> dict[str, Any]:
    """Fallback public Instagram scraping using httpx."""
    headers = {
        "User-Agent": config.USER_AGENT,
        "X-IG-App-ID": "936619743392459",
        "Accept": "*/*",
        "Referer": f"https://www.instagram.com/{username}/",
    }
    profile_url = f"https://www.instagram.com/{username}/"

    with httpx.Client(timeout=config.HTTP_TIMEOUT_SECONDS, headers=headers, follow_redirects=True) as client:
        response = client.get(
            "https://www.instagram.com/api/v1/users/web_profile_info/",
            params={"username": username},
        )
        if response.status_code == 200:
            try:
                return _extract_profile_from_public_api(response.json(), username)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Falha ao interpretar endpoint público do Instagram para @%s: %s", username, exc)

        html_response = client.get(profile_url)
        html_response.raise_for_status()
        html = html_response.text

    data = _empty_instagram_data(username)
    data.update(
        {
            "collection_status": "partial",
            "source": "instagram_public_html",
            "used_apify": False,
        }
    )

    description_match = re.search(
        r'content="([\d\.,]+)\s+Followers,\s+([\d\.,]+)\s+Following,\s+([\d\.,]+)\s+Posts',
        html,
        re.IGNORECASE,
    )
    if description_match:
        data["followers_count"] = int(description_match.group(1).replace(".", "").replace(",", ""))
        data["following_count"] = int(description_match.group(2).replace(".", "").replace(",", ""))
        data["posts_count"] = int(description_match.group(3).replace(".", "").replace(",", ""))

    biography_match = re.search(r'"biography":"(.*?)"', html)
    if biography_match:
        data["biography"] = biography_match.group(1).encode("utf-8").decode("unicode_escape")

    external_url_match = re.search(r'"external_url":"(.*?)"', html)
    if external_url_match:
        extracted = external_url_match.group(1).encode("utf-8").decode("unicode_escape")
        data["external_url"] = extracted.replace("\\/", "/")

    category_match = re.search(r'"category_name":"(.*?)"', html)
    if category_match:
        data["category"] = category_match.group(1).encode("utf-8").decode("unicode_escape")

    data["error"] = ""
    return _finalize_instagram_data(data)


def get_instagram_data(username: str | None, prefer_apify: bool = True) -> dict[str, Any]:
    """Collect Instagram profile data and derived metrics.

    Parameters
    ----------
    username:
        Instagram username to inspect.
    prefer_apify:
        When ``True`` and an Apify token exists, try Apify first for the richer
        dataset and use public scraping only as fallback.

    Returns
    -------
    dict[str, Any]
        Instagram profile metrics, latest post stats, engagement heuristics, and
        collection metadata.
    """
    if not username:
        return _empty_instagram_data()

    normalized_username = username.strip().lstrip("@")
    if not normalized_username:
        return _empty_instagram_data()

    if prefer_apify and config.APIFY_TOKEN:
        try:
            return _fetch_instagram_via_apify(normalized_username)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Apify indisponível para @%s, tentando fallback: %s", normalized_username, exc)

    try:
        return _fetch_instagram_public(normalized_username)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falha ao coletar Instagram de @%s: %s", normalized_username, exc)
        data = _empty_instagram_data(normalized_username)
        data.update(
            {
                "collection_status": "error_coleta",
                "source": "error",
                "error": str(exc),
            }
        )
        return data
