"""Message generation using Gemini with deterministic fallback."""

from __future__ import annotations

import json
import logging
import re
import warnings
from typing import Any

from . import config

logger = logging.getLogger(__name__)

try:
    from google import genai as google_genai
except Exception:  # noqa: BLE001
    google_genai = None

try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        import google.generativeai as google_generativeai
except Exception:  # noqa: BLE001
    google_generativeai = None


def _extract_reference_from_captions(captions: list[str]) -> tuple[str, str]:
    """Pull a specific hook from recent captions when possible."""
    for caption in captions:
        lowered = caption.lower()
        for keyword in config.VISUAL_MENU_KEYWORDS:
            if keyword in lowered:
                snippet = re.sub(r"\s+", " ", caption).strip()
                sentence = re.split(r"[.!?\n]", snippet)[0].strip()
                sentence = sentence[:90].rstrip(" ,;:")
                return keyword, sentence or keyword
    return "", ""


def _sanitize_message_lines(text: str) -> str:
    """Enforce short, clean message formatting."""
    cleaned = text.strip().replace("\r\n", "\n").replace("\r", "\n")
    for banned in config.BANNED_MESSAGE_WORDS:
        cleaned = re.sub(rf"\b{re.escape(banned)}\b", "ajuste", cleaned, flags=re.IGNORECASE)
    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    if len(lines) > 4:
        lines = lines[:3] + [" ".join(lines[3:])]
    return "\n".join(lines[:4])


def _fallback_messages(place_data: dict[str, Any], ig_data: dict[str, Any], score_data: dict[str, Any]) -> dict[str, str]:
    """Build deterministic outreach copy when Gemini is unavailable."""
    name = place_data.get("name", "o restaurante")
    neighborhood = place_data.get("neighborhood") or place_data.get("city", "")
    captions = ig_data.get("recent_captions") or []
    keyword, sentence = _extract_reference_from_captions(captions)
    link_type = place_data.get("current_link_type") or ""

    if sentence:
        opening = f"Vi esse post de vocês falando de {keyword} e curti a forma como a {name} se posiciona."
        angle = "caption_especifica"
    elif neighborhood:
        opening = f"Vi a {name} em {neighborhood} e o perfil de vocês passa bastante cuidado com imagem."
        angle = "bairro_e_marca"
    else:
        opening = f"Passei pelo perfil da {name} e achei a marca bem redonda pra proposta que vocês têm."
        angle = "marca"

    second_line = "Preparei uma demo rápida de site pensando no momento da marca de vocês."
    if link_type:
        second_line = f"Preparei uma demo rápida de site pensando em tirar a dependência do {link_type}."

    whatsapp_message = _sanitize_message_lines(
        "\n".join(
            [
                opening,
                second_line,
                "Ficou bem alinhada com os pontos fortes que vi no perfil de vocês.",
                "Posso te mandar pra ver se faz sentido?",
            ]
        )
    )
    instagram_dm = _sanitize_message_lines(
        "\n".join(
            [
                opening,
                "Montei uma demo rápida de site inspirada no perfil de vocês.",
                "Se quiser, te mando por aqui.",
            ]
        )
    )
    subject_email = f"Demo de site para {name}"
    if score_data.get("classification") == "HOT":
        angle = f"{angle}_hot"
    return {
        "whatsapp_message": whatsapp_message,
        "instagram_dm": instagram_dm,
        "subject_email": subject_email,
        "approach_angle": angle,
    }


def _extract_json_object(raw_text: str) -> dict[str, Any] | None:
    """Extract a JSON object from model output."""
    if not raw_text:
        return None
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _gemini_prompt(place_data: dict[str, Any], ig_data: dict[str, Any], score_data: dict[str, Any]) -> str:
    """Create the final prompt sent to Gemini."""
    captions = ig_data.get("recent_captions") or ["", "", ""]
    neighborhood = place_data.get("neighborhood") or "não identificado"
    city = place_data.get("city") or "não identificado"
    return f"""
Você é um especialista em vendas consultivas B2B para o mercado de restaurantes premium brasileiros.
Escreva uma mensagem de primeiro contato via WhatsApp para o proprietário do restaurante descrito abaixo.

REGRAS OBRIGATÓRIAS:
1. Máximo 4 linhas de texto. Sem emojis excessivos (máximo 1).
2. Referenciar algo ESPECÍFICO e REAL do restaurante (um prato pelo nome, o bairro, algo das captions).
3. NÃO revelar que é automação. Escrever como pessoa real.
4. NÃO citar preço, não fazer pitch completo.
5. Criar curiosidade com "preparei uma demo" sem mostrar.
6. Terminar com pergunta simples de baixo comprometimento.
7. Tom: informal mas profissional. PT-BR coloquial.
8. NÃO usar palavras: solução, incrível, incrível, transformar, potencializar, alavancar, revolucionar.
9. Responda APENAS com JSON válido.

Formato JSON:
{{
  "whatsapp_message": "...",
  "instagram_dm": "...",
  "subject_email": "...",
  "approach_angle": "..."
}}

Dados do restaurante:
- Nome: {place_data.get("name", "")}
- Bairro: {neighborhood}
- Cidade: {city}
- Seguidores: {ig_data.get("followers_count", "n/d")}
- Engajamento: {ig_data.get("engagement_rate", "n/d")}%
- Tipo de link atual: {place_data.get("current_link_type", "")}
- Categoria Maps: {place_data.get("category", "")}
- Categoria Instagram: {ig_data.get("category", "")}
- Score: {score_data.get("total_score", 0)}
- Pontos fortes: {", ".join(score_data.get("key_strengths") or [])}
- Caption 1: {captions[0] if len(captions) > 0 else ""}
- Caption 2: {captions[1] if len(captions) > 1 else ""}
- Caption 3: {captions[2] if len(captions) > 2 else ""}

Exemplos de abertura forte (adaptar ao contexto):
- "Vi o [prato específico] de vocês no Instagram..."
- "Passei em frente à [nome] outro dia em [bairro]..."
- "Alguém me indicou a [nome] essa semana..."

Exemplos de fechamento forte:
- "Preparei uma versão do site de vocês. Posso mandar?"
- "Montei algo baseado no perfil de vocês. Vale dar uma olhada?"
- "Fiz uma demo rápida pra vocês. Curioso pra saber o que acha."
""".strip()


def _generate_with_google_genai(prompt: str, model_name: str) -> str:
    """Generate content with the modern Google GenAI SDK."""
    if google_genai is None:
        raise RuntimeError("google-genai não instalado")
    client = google_genai.Client(api_key=config.GEMINI_API_KEY)
    response = client.models.generate_content(model=model_name, contents=prompt)
    return getattr(response, "text", "") or ""


def _generate_with_google_generativeai(prompt: str, model_name: str) -> str:
    """Generate content with the older google-generativeai SDK."""
    if google_generativeai is None:
        raise RuntimeError("google-generativeai não instalado")
    google_generativeai.configure(api_key=config.GEMINI_API_KEY)
    model = google_generativeai.GenerativeModel(model_name=model_name)
    response = model.generate_content(prompt)
    return getattr(response, "text", "") or ""


def generate_message(place_data: dict[str, Any], ig_data: dict[str, Any], score_data: dict[str, Any]) -> dict[str, str]:
    """Generate WhatsApp/DM outreach copy from lead context.

    Parameters
    ----------
    place_data:
        Place record enriched with current link type and location.
    ig_data:
        Instagram metrics and recent captions.
    score_data:
        Lead score output containing score and strengths.

    Returns
    -------
    dict[str, str]
        WhatsApp message, Instagram DM version, optional email subject, and
        approach angle used for the copy.
    """
    if not config.GEMINI_API_KEY:
        return _fallback_messages(place_data, ig_data, score_data)

    prompt = _gemini_prompt(place_data, ig_data, score_data)
    models_to_try = [config.GEMINI_MODEL, *config.GEMINI_FALLBACK_MODELS]

    for model_name in models_to_try:
        for generator in (_generate_with_google_genai, _generate_with_google_generativeai):
            try:
                raw_text = generator(prompt, model_name)
                parsed = _extract_json_object(raw_text)
                if not parsed:
                    continue
                return {
                    "whatsapp_message": _sanitize_message_lines(parsed.get("whatsapp_message", "")),
                    "instagram_dm": _sanitize_message_lines(parsed.get("instagram_dm", "")),
                    "subject_email": parsed.get("subject_email", "")[:120],
                    "approach_angle": parsed.get("approach_angle", model_name),
                }
            except Exception as exc:  # noqa: BLE001
                logger.warning("Gemini falhou com modelo %s: %s", model_name, exc)

    return _fallback_messages(place_data, ig_data, score_data)
