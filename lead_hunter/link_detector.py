"""Website analysis logic to decide whether a business has a professional site."""

from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from . import config

logger = logging.getLogger(__name__)

WHATSAPP_NUMBER_REGEX = re.compile(
    r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=|\+?55[\s\-]?)?(\d{10,13})"
)
INSTAGRAM_URL_REGEX = re.compile(
    r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9._]{1,30})/?", re.IGNORECASE
)


def _ensure_scheme(url: str) -> str:
    """Ensure the URL contains a scheme."""
    cleaned = (url or "").strip()
    if not cleaned:
        return ""
    if cleaned.startswith("//"):
        return f"https:{cleaned}"
    if not cleaned.startswith(("http://", "https://")):
        return f"https://{cleaned}"
    return cleaned


def _normalize_domain(url_or_domain: str) -> str:
    """Normalize a domain removing common prefixes."""
    parsed = urlparse(url_or_domain if "://" in url_or_domain else f"https://{url_or_domain}")
    domain = parsed.netloc.lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _domain_matches(domain: str, candidates: set[str] | list[str]) -> bool:
    """Check whether a domain matches or is a subdomain of one of the candidates."""
    return any(domain == candidate or domain.endswith(f".{candidate}") for candidate in candidates)


def _classify_known_domain(domain: str) -> str | None:
    """Classify domains that directly imply no professional site."""
    if _domain_matches(domain, config.WHATSAPP_DOMAINS):
        return "whatsapp"
    if _domain_matches(domain, config.BIO_LINK_DOMAINS):
        if "linktr.ee" in domain:
            return "linktree"
        return "bio_link"
    if _domain_matches(domain, config.DELIVERY_DOMAINS):
        return "ifood" if "ifood.com.br" in domain else "delivery_app"
    if _domain_matches(domain, config.SOCIAL_DOMAINS):
        return "social_profile"
    return None


def _extract_visible_text(soup: BeautifulSoup) -> str:
    """Extract visible text from a document."""
    for element in soup(["script", "style", "noscript", "svg"]):
        element.extract()
    return " ".join(chunk.strip() for chunk in soup.stripped_strings if chunk.strip())


def _extract_internal_links(soup: BeautifulSoup, final_domain: str, base_url: str) -> set[str]:
    """Return unique internal links found on the page."""
    links: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, anchor["href"])
        parsed = urlparse(href)
        domain = _normalize_domain(parsed.netloc or final_domain)
        if domain == final_domain and parsed.path:
            links.add(parsed.path.rstrip("/") or "/")
    return links


def _find_instagram_url(soup: BeautifulSoup) -> str:
    """Return the first Instagram URL found in the page."""
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if "instagram.com/" in href.lower():
            return href

    match = INSTAGRAM_URL_REGEX.search(str(soup))
    if match:
        return f"https://www.instagram.com/{match.group(1)}/"
    return ""


def _find_whatsapp_number(html_text: str) -> str:
    """Return the first WhatsApp number found in the page text or code."""
    match = WHATSAPP_NUMBER_REGEX.search(html_text)
    return match.group(1) if match else ""


def _contains_keywords(text: str, keywords: list[str]) -> bool:
    """Case-insensitive keyword lookup."""
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def analyze_website(url: str | None) -> dict[str, Any]:
    """Analyze a website URL and classify whether it is a real professional site.

    Parameters
    ----------
    url:
        URL captured from Google Maps or Instagram bio.

    Returns
    -------
    dict[str, Any]
        Structured website analysis including site classification, redirect
        result, Instagram/WhatsApp hints, and confidence score.
    """
    result: dict[str, Any] = {
        "has_professional_site": False,
        "link_type": "sem_link",
        "original_url": url or "",
        "final_url": "",
        "instagram_url": "",
        "whatsapp_number": "",
        "confidence": 1.0 if not url else 0.0,
        "site_signals": {},
        "load_time_seconds": None,
    }

    if not url or not str(url).strip():
        return result

    normalized_url = _ensure_scheme(str(url))
    result["original_url"] = normalized_url
    original_domain = _normalize_domain(normalized_url)
    known_type = _classify_known_domain(original_domain)
    if known_type:
        result.update(
            {
                "has_professional_site": False,
                "link_type": known_type,
                "final_url": normalized_url,
                "confidence": 0.99,
            }
        )
        return result

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=config.HTTP_TIMEOUT_SECONDS,
            headers={"User-Agent": config.USER_AGENT},
        ) as client:
            started_at = time.perf_counter()
            response = client.get(normalized_url)
            load_time = time.perf_counter() - started_at
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falha ao analisar website %s: %s", normalized_url, exc)
        result.update(
            {
                "link_type": "site_inacessivel",
                "final_url": normalized_url,
                "confidence": 0.35,
            }
        )
        return result

    final_url = str(response.url)
    final_domain = _normalize_domain(final_url)
    html = response.text or ""

    result["final_url"] = final_url
    result["load_time_seconds"] = round(load_time, 3)
    result["whatsapp_number"] = _find_whatsapp_number(html)

    redirect_type = _classify_known_domain(final_domain)
    if redirect_type:
        result.update(
            {
                "link_type": redirect_type,
                "confidence": 0.97,
            }
        )
        return result

    soup = BeautifulSoup(html, "html.parser")
    visible_text = _extract_visible_text(soup)
    html_lower = html.lower()
    meta_generator = ""
    generator_tag = soup.find("meta", attrs={"name": re.compile("generator", re.IGNORECASE)})
    if generator_tag:
        meta_generator = str(generator_tag.get("content", "")).lower()

    instagram_url = _find_instagram_url(soup)
    result["instagram_url"] = instagram_url

    internal_links = _extract_internal_links(soup, final_domain, final_url)
    internal_pages = len(internal_links)
    word_count = len(re.findall(r"\w+", visible_text))
    section_count = len(soup.find_all(["section", "article", "nav", "main"]))
    has_menu = _contains_keywords(visible_text, config.MENU_KEYWORDS)
    has_contact = _contains_keywords(visible_text, config.CONTACT_KEYWORDS)
    has_about = _contains_keywords(visible_text, config.ABOUT_KEYWORDS)
    has_location = _contains_keywords(visible_text, config.LOCATION_KEYWORDS)
    has_analytics = any(
        marker in html_lower
        for marker in [
            "googletagmanager.com",
            "google-analytics.com",
            "gtag(",
            "gtm-",
            "ga('create'",
        ]
    )
    framework_markers = [
        "_next/",
        "__next",
        "vite/client",
        "__nuxt",
        "astro-island",
        "webpack",
        "reactroot",
    ]
    has_modern_framework = any(marker in html_lower for marker in framework_markers)
    delivery_links = 0
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].lower()
        if any(domain in href for domain in config.DELIVERY_DOMAINS):
            delivery_links += 1

    builder_subdomain = _domain_matches(final_domain, config.SITE_BUILDER_DOMAINS)
    builder_generator = any(
        marker in meta_generator for marker in ["wix", "wordpress.com", "squarespace", "weebly", "site123"]
    )
    thin_fast_site = load_time < 0.5 and word_count < 500

    professional_score = sum(
        [
            1 if section_count >= 5 else 0,
            1 if internal_pages >= 3 else 0,
            1 if has_menu else 0,
            1 if has_contact else 0,
            1 if has_about else 0,
            1 if has_location else 0,
            1 if has_analytics else 0,
            1 if has_modern_framework else 0,
        ]
    )
    weak_score = sum(
        [
            1 if builder_subdomain else 0,
            1 if builder_generator else 0,
            1 if internal_pages < 3 else 0,
            1 if section_count < 3 else 0,
            1 if not has_menu else 0,
            1 if delivery_links >= 1 else 0,
            1 if thin_fast_site else 0,
        ]
    )

    result["site_signals"] = {
        "word_count": word_count,
        "section_count": section_count,
        "internal_pages": internal_pages,
        "has_menu": has_menu,
        "has_contact": has_contact,
        "has_about": has_about,
        "has_location": has_location,
        "has_analytics": has_analytics,
        "has_modern_framework": has_modern_framework,
        "delivery_links": delivery_links,
        "builder_subdomain": builder_subdomain,
        "builder_generator": builder_generator,
    }

    if builder_subdomain or builder_generator:
        result.update(
            {
                "has_professional_site": False,
                "link_type": "wix_basic",
                "confidence": 0.82,
            }
        )
        return result

    if delivery_links >= 1 and not has_menu and internal_pages < 3:
        result.update(
            {
                "has_professional_site": False,
                "link_type": "delivery_app",
                "confidence": 0.75,
            }
        )
        return result

    if professional_score >= 4 and has_menu and (has_contact or has_location):
        result.update(
            {
                "has_professional_site": True,
                "link_type": "site_real",
                "confidence": 0.9,
            }
        )
        return result

    if weak_score >= 4 or thin_fast_site:
        result.update(
            {
                "has_professional_site": False,
                "link_type": "site_basico",
                "confidence": 0.7,
            }
        )
        return result

    result.update(
        {
            "has_professional_site": False,
            "link_type": "site_basico",
            "confidence": 0.55,
        }
    )
    return result
