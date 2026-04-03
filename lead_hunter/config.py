"""Centralized configuration for the lead hunter project."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
CHECKPOINT_PATH = DATA_DIR / "checkpoint.json"
LEADS_SNAPSHOT_PATH = DATA_DIR / "latest_qualified_leads.json"
LOG_FILE_PATH = LOGS_DIR / "lead_hunter.log"
DEFAULT_SERVICE_ACCOUNT_FILE = BASE_DIR / "service_account.json"


def _load_api_text_values() -> dict[str, str]:
    """Load optional key/value secrets from a local API.txt file."""
    api_file = BASE_DIR / "API.txt"
    values: dict[str, str] = {}
    if not api_file.exists():
        return values

    for raw_line in api_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            values[key] = value
    return values


_API_TEXT_VALUES = _load_api_text_values()


def _resolve_secret(name: str, default: str = "") -> str:
    """Resolve configuration values from env vars, API.txt, or defaults."""
    return (
        os.getenv(name)
        or _API_TEXT_VALUES.get(name)
        or default
    )

GOOGLE_MAPS_API_KEY = _resolve_secret("GOOGLE_MAPS_API_KEY")
APIFY_TOKEN = _resolve_secret("APIFY_TOKEN")
GEMINI_API_KEY = _resolve_secret("GEMINI_API_KEY")
GOOGLE_SHEETS_ID = _resolve_secret("GOOGLE_SHEETS_ID")
NOTIFICATION_EMAIL = _resolve_secret("NOTIFICATION_EMAIL")

SMTP_EMAIL = _resolve_secret("SMTP_EMAIL")
SMTP_APP_PASSWORD = _resolve_secret("SMTP_APP_PASSWORD")
GOOGLE_SERVICE_ACCOUNT_JSON = _resolve_secret("GOOGLE_SERVICE_ACCOUNT_JSON")
GOOGLE_SERVICE_ACCOUNT_FILE = _resolve_secret("GOOGLE_SERVICE_ACCOUNT_FILE", str(DEFAULT_SERVICE_ACCOUNT_FILE))

# Defaulting to the current Flash family model for better first-run compatibility,
# while keeping Gemini 2.0 Flash as an automatic fallback when available.
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_FALLBACK_MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
]

TARGET_CITIES = [
    "Vila Madalena, São Paulo",
    "Pinheiros, São Paulo",
    "Itaim Bibi, São Paulo",
    "Jardins, São Paulo",
    "Moema, São Paulo",
    "Vila Olímpia, São Paulo",
    "Perdizes, São Paulo",
    "Consolação, São Paulo",
    "Brooklin, São Paulo",
    "Campo Belo, São Paulo",
    "Ipanema, Rio de Janeiro",
    "Leblon, Rio de Janeiro",
    "Botafogo, Rio de Janeiro",
    "Barra da Tijuca, Rio de Janeiro",
    "Savassi, Belo Horizonte",
    "Batel, Curitiba",
    "Moinhos de Vento, Porto Alegre",
]

TARGET_CATEGORIES = [
    "hamburgueria artesanal",
    "smash burger",
    "burger artesanal",
    "pizzaria artesanal",
    "pizza napolitana",
    "churrascaria",
    "espetinho gourmet",
    "sushi delivery",
    "tapiocaria artesanal",
    "comida japonesa artesanal",
    "restaurante contemporâneo",
    "bistrô",
    "bar e cozinha",
    "gastrobar",
]

NO_SITE_DOMAINS = [
    "linktr.ee",
    "link.bio",
    "beacons.ai",
    "taplink.cc",
    "bio.site",
    "linkin.bio",
    "campsite.bio",
    "allmylinks.com",
    "lnk.bio",
    "solo.to",
    "wa.me",
    "api.whatsapp.com",
    "cardapio.app",
    "goomer.com.br",
    "anotaai.com",
    "ifood.com.br",
    "rappi.com.br",
    "instagram.com",
    "facebook.com",
]

PREMIUM_KEYWORDS = [
    "artesanal",
    "smash",
    "wagyu",
    "angus",
    "gourmet",
    "blend",
    "premium",
    "craft",
    "especial",
    "autoral",
    "contemporâneo",
    "bistrô",
    "gastro",
    "burger",
    "burguer",
]

PREMIUM_NEIGHBORHOODS = [
    "vila madalena",
    "pinheiros",
    "itaim",
    "jardins",
    "moema",
    "vila olímpia",
    "consolação",
    "higienópolis",
    "ipanema",
    "leblon",
    "botafogo",
    "savassi",
    "batel",
    "moinhos",
    "funcionários",
]

MAPS_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
MAPS_PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
MAPS_TEXT_SEARCH_FIELDS = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.businessStatus",
        "places.primaryTypeDisplayName",
        "nextPageToken",
    ]
)
MAPS_PLACE_DETAILS_FIELDS = ",".join(
    [
        "id",
        "displayName",
        "formattedAddress",
        "internationalPhoneNumber",
        "nationalPhoneNumber",
        "websiteUri",
        "rating",
        "userRatingCount",
        "regularOpeningHours",
        "currentOpeningHours",
        "priceLevel",
        "editorialSummary",
        "reviews",
        "businessStatus",
        "googleMapsUri",
        "primaryType",
        "primaryTypeDisplayName",
        "shortFormattedAddress",
    ]
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36"
)

MAPS_REQUEST_DELAY_SECONDS = 0.5
MAPS_PAGE_DELAY_SECONDS = 2.0
REQUEST_DELAY_RANGE_SECONDS = (1.0, 2.0)
GEMINI_DELAY_SECONDS = 1.0
APIFY_MAX_CALLS_PER_SESSION = 50
CHECKPOINT_EVERY = 10
HTTP_TIMEOUT_SECONDS = 10
GOOGLE_MAPS_PAGE_SIZE = 20
MAX_GOOGLE_MAPS_PAGES = 3

SHEETS_HEADERS = [
    "🌡️ Status",
    "Score",
    "Nome do Restaurante",
    "Categoria",
    "Bairro",
    "Cidade",
    "Telefone",
    "Instagram",
    "Tipo de link atual",
    "Seguidores Instagram",
    "Taxa de Engajamento (%)",
    "Avaliações Google",
    "Rating Google",
    "Último post (dias atrás)",
    "Pontos Fortes",
    "Mensagem WhatsApp",
    "Mensagem Instagram DM",
    "Data de coleta",
    "Status de contato",
    "Resultado",
]

BIO_LINK_DOMAINS = {
    "linktr.ee",
    "link.bio",
    "beacons.ai",
    "taplink.cc",
    "bio.site",
    "linkin.bio",
    "campsite.bio",
    "allmylinks.com",
    "lnk.bio",
    "solo.to",
}
WHATSAPP_DOMAINS = {"wa.me", "api.whatsapp.com", "whatsapp.com"}
DELIVERY_DOMAINS = {
    "ifood.com.br",
    "rappi.com.br",
    "cardapio.app",
    "goomer.com.br",
    "anotaai.com",
}
SOCIAL_DOMAINS = {"instagram.com", "facebook.com"}
SITE_BUILDER_DOMAINS = {
    "wixsite.com",
    "wordpress.com",
    "squarespace.com",
    "weebly.com",
    "webflow.io",
    "site123.me",
}

MENU_KEYWORDS = [
    "cardápio",
    "cardapio",
    "menu",
    "pedido",
    "pedidos",
    "combo",
    "hambúrguer",
    "hamburguer",
    "burguer",
    "burger",
    "pizza",
    "rodízio",
    "rodizio",
    "sushi",
    "uramaki",
    "nigiri",
    "tapioca",
    "prato",
    "sobremesa",
]
CONTACT_KEYWORDS = [
    "contato",
    "fale conosco",
    "reservas",
    "reserva",
    "telefone",
    "whatsapp",
]
ABOUT_KEYWORDS = [
    "sobre",
    "nossa história",
    "nossa historia",
    "quem somos",
    "autoral",
]
LOCATION_KEYWORDS = [
    "endereço",
    "endereco",
    "localização",
    "localizacao",
    "como chegar",
    "bairro",
]
VISUAL_MENU_KEYWORDS = [
    "burger",
    "burguer",
    "smash",
    "blend",
    "pizza",
    "napolitana",
    "sushi",
    "uramaki",
    "nigiri",
    "ceviche",
    "costela",
    "picanha",
    "tapioca",
    "sobremesa",
    "milkshake",
    "drinque",
    "coquetel",
]
RESTAURANT_CATEGORY_KEYWORDS = [
    "restaurant",
    "restaurante",
    "food",
    "burger",
    "pizza",
    "sushi",
    "bar",
    "delivery",
    "bistrô",
    "bistro",
]
CHAIN_KEYWORDS = [
    "mcdonald",
    "burger king",
    "subway",
    "pizza hut",
    "domino",
    "giraffas",
    "habib",
    "outback",
    "coco bambu",
    "madero",
    "jeronimo",
    "bob's",
    "bobs",
]
BANNED_MESSAGE_WORDS = [
    "solução",
    "incrível",
    "incrivel",
    "transformar",
    "potencializar",
    "alavancar",
    "revolucionar",
]
