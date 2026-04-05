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


def _link_type_label_short(link_type: str) -> str:
    """Short label for link type used inside messages."""
    return {
        "linktree": "Linktree",
        "bio_link": "bio link",
        "whatsapp": "WhatsApp direto",
        "ifood": "iFood",
        "delivery_app": "app de delivery",
        "social_profile": "rede social",
    }.get(link_type, "link atual")


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
    reviews = place_data.get("user_ratings_total", "")
    followers = ig_data.get("followers_count", "")

    if sentence:
        opening = f"Vi o post de vocês sobre {keyword} — fui pesquisar a {name} depois disso."
        ig_opening = f"Esse post sobre {keyword} me chamou atenção — perfil forte, site ainda não acompanha."
        angle = "caption_especifica"
    elif neighborhood:
        opening = f"Pesquisei a {name} em {neighborhood} — marca sólida, presença digital ainda tá abaixo disso."
        ig_opening = f"Feed da {name} tem identidade clara — só o site ainda não chegou nesse nível."
        angle = "bairro"
    else:
        opening = f"Pesquisei a {name} — avaliações boas, mas a presença digital ainda não acompanha o peso da marca."
        ig_opening = f"Perfil da {name} tem posicionamento claro — o site ainda não chegou nesse nível."
        angle = "marca"

    if link_type and link_type not in ("sem_link", "site_real"):
        pitch = f"Montei uma demo de site pra vocês tirando a dependência do {_link_type_label_short(link_type)}."
    else:
        pitch = "Montei uma demo de site pensada pra vocês. Posso mandar o link?"

    whatsapp_message = _sanitize_message_lines(
        "\n".join([opening, pitch, "Posso mandar o link?"])
    )
    whatsapp_followup = _sanitize_message_lines(
        "\n".join([
            f"O demo que fiz pra {name} ficou bem bacana — pode ter sido que não chegou pra quem decide.",
            "Se não for você, pode encaminhar? Vale 2 minutos.",
        ])
    )
    instagram_dm = _sanitize_message_lines(
        "\n".join([ig_opening, "Fiz uma demo de site pra vocês — posso mandar o link?"])
    )

    social_proof = ""
    if reviews:
        social_proof += f"{reviews} avaliações no Google"
    if followers:
        social_proof += (", " if social_proof else "") + f"{followers} seguidores no Instagram"

    email_body = (
        f"{name},\n\n"
        f"Dei uma olhada no perfil de vocês{f' — {social_proof}' if social_proof else ''} "
        f"e a marca está bem construída. Mas a presença digital ainda não acompanha esse peso.\n\n"
        f"Separei uma referência do que isso poderia ser:\n"
        f"→ https://aura-burger.vercel.app/\n\n"
        f"A lógica aqui é posicionamento e experiência — o site que converte antes do cardápio. "
        f"A ideia não é substituir o que vocês usam, é mostrar um padrão diferente de apresentação.\n\n"
        f"Se fizer sentido, é só responder — explico em dois parágrafos como isso se aplica à estrutura de vocês.\n\n"
        f"Wesley\nWX Digital Studio"
    )

    if score_data.get("classification") == "HOT":
        angle = f"{angle}_hot"
    return {
        "whatsapp_message": whatsapp_message,
        "whatsapp_followup": whatsapp_followup,
        "instagram_dm": instagram_dm,
        "subject_email": f"{name} — uma referência que separei para vocês",
        "email_body": email_body,
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
    name = place_data.get("name", "o restaurante")
    link_type = place_data.get("current_link_type") or "sem site"
    strengths = ", ".join(score_data.get("key_strengths") or [])
    return f"""
Você é freelancer de web para restaurantes premium no Brasil. Vende sites profissionais, trabalha de forma independente.
A demo que você usa como referência está em: https://aura-burger.vercel.app/
Sua assinatura é: Wesley | WX Digital Studio

CONTEXTO DO LEAD:
- Nome: {name}
- Bairro: {neighborhood} — Cidade: {city}
- Link atual: {link_type} (este é o problema que você resolve com um site profissional)
- Instagram: @{ig_data.get("username", "n/d")} — {ig_data.get("followers_count", "n/d")} seguidores, {ig_data.get("engagement_rate", "n/d")}% engajamento
- Google: {place_data.get("rating", "n/d")}★ com {place_data.get("user_ratings_total", "n/d")} avaliações
- Pontos fortes: {strengths}
- Caption recente 1: {captions[0] if len(captions) > 0 else ""}
- Caption recente 2: {captions[1] if len(captions) > 1 else ""}
- Caption recente 3: {captions[2] if len(captions) > 2 else ""}

ESCREVA 4 mensagens:

== MENSAGEM 1 — PRIMEIRO CONTATO (WhatsApp) ==
Objetivo: chegar no DONO. Quem recebe pode ser funcionário — a mensagem precisa ser boa o suficiente para ser encaminhada.
Regras:
- PROIBIDO abrir com "Oi", "Olá", "Bom dia", "Tudo bem?" ou qualquer cumprimento. Começa direto na observação.
- Linha 1: observação ESPECÍFICA que prova que você pesquisou — cite o nome do prato/produto das captions, o bairro, ou dado real (avaliações, seguidores). Nunca genérico.
- Linha 2: o gancho — "montei um site/demo pra vocês" com uma referência ao que está faltando (ex: o link atual, a falta de site à altura da marca). Não explique o que é o site.
- Linha 3: CTA de sim/não, direto: "posso mandar o link?" ou "vale dar uma olhada?". Nada mais.
- Máximo 1 emoji no total. Tom: PT-BR coloquial, confiante, como freelancer que pesquisou de verdade.

== MENSAGEM 2 — FOLLOW-UP (enviar se não responder em 3 dias) ==
Objetivo: reengajar com ângulo diferente, sem parecer insistente.
Regras:
- PROIBIDO abrir com "Oi", "Olá" ou qualquer cumprimento.
- 2 linhas no máximo. Tom ainda mais casual — como se fosse uma segunda mensagem num conversa já aberta.
- Novo gancho diferente da msg 1: pode ser "o demo ficou bem bacana", "tive uma ideia para vocês", ou curiosidade nova.
- Reconheça que pode não ter chegado à pessoa certa: "se não for com você que decide, pode encaminhar?"
- Sem "seguindo minha mensagem anterior" nem referência direta ao que foi dito antes.

== MENSAGEM 3 — INSTAGRAM DM ==
Objetivo: versão adaptada para DM. Tom mais jovem e de Instagram. Máximo 2 linhas.
Regras:
- PROIBIDO abrir com "Oi", "Olá" ou cumprimentos.
- Abre com observação sobre o perfil deles (visual, conteúdo, estética) — algo que faça sentido vindo de quem viu o feed.
- Segunda linha: o gancho do demo ou da ideia, com CTA direto.
- Pode usar 1 emoji se encaixar naturalmente.

== MENSAGEM 4 — E-MAIL DE ABORDAGEM ==
Objetivo: abordagem profissional por e-mail para quando o e-mail de contato for encontrado.
Regras:
- Abra direto com o nome do restaurante, sem "Bom dia" nem "tudo bem?".
- Segunda linha: observação com dados reais (avaliações Google e/ou seguidores Instagram) + problema concreto (presença digital não acompanha o peso da marca).
- Terceira parte: apresente o link da demo com uma seta (→ https://aura-burger.vercel.app/) e explique brevemente que a lógica é posicionamento, não substituição do que já usam.
- Feche com CTA suave: "se fizer sentido, é só responder — explico como isso se aplica a vocês".
- Assine como: Wesley\\nWX Digital Studio
- Máximo 110 palavras no corpo. Tom profissional mas direto.
- NÃO coloque o assunto dentro do corpo.

PALAVRAS PROIBIDAS em todas: solução, incrível, transformar, potencializar, alavancar, revolucionar, resultado.

Responda APENAS com JSON válido:
{{
  "whatsapp_message": "...",
  "whatsapp_followup": "...",
  "instagram_dm": "...",
  "subject_email": "{name} — uma referência que separei para vocês",
  "email_body": "...",
  "approach_angle": "descrição curta do ângulo (ex: caption_especifica, bairro_referencia, link_atual)"
}}
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
                    "whatsapp_followup": _sanitize_message_lines(parsed.get("whatsapp_followup", "")),
                    "instagram_dm": _sanitize_message_lines(parsed.get("instagram_dm", "")),
                    "subject_email": parsed.get("subject_email", "")[:120],
                    "email_body": (parsed.get("email_body", "") or "").strip(),
                    "approach_angle": parsed.get("approach_angle", model_name),
                }
            except Exception as exc:  # noqa: BLE001
                logger.warning("Gemini falhou com modelo %s: %s", model_name, exc)

    return _fallback_messages(place_data, ig_data, score_data)
