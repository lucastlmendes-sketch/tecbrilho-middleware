import logging
import os
from typing import List, Dict, Any, Optional

import httpx

logger = logging.getLogger(__name__)

BOTCONVERSA_API_BASE = os.getenv(
    "BOTCONVERSA_API_BASE", "https://backend.botconversa.com.br/api/v1"
)
BOTCONVERSA_API_TOKEN = os.getenv("BOTCONVERSA_API_TOKEN", "")


def _get_headers() -> Dict[str, str]:
    if not BOTCONVERSA_API_TOKEN:
        raise RuntimeError("BOTCONVERSA_API_TOKEN não configurado")
    # Ajuste aqui se o esquema de auth for diferente (Bearer, JWT, etc.)
    return {
        "Authorization": f"Token {BOTCONVERSA_API_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _safe_request(method: str, url: str, **kwargs) -> Optional[httpx.Response]:
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.request(method, url, **kwargs)
        if resp.status_code >= 400:
            logger.warning(
                "Erro ao chamar BotConversa (%s %s): %s %s",
                method,
                url,
                resp.status_code,
                resp.text,
            )
            return None
        return resp
    except Exception as exc:
        logger.exception("Exceção ao chamar BotConversa: %s", exc)
        return None


# ---------------------------
# Funções de alto nível
# ---------------------------


def fetch_contact(
    contact_id: Optional[str] = None,
    phone: Optional[str] = None,
) -> Dict[str, Any]:
    """Busca dados do contato no BotConversa.

    Tenta primeiro pelo contact_id (se existir), senão tenta pelo telefone.
    O formato exato do JSON pode variar conforme a API, então aqui tentamos
    mapear alguns campos comuns: name, phone, tags, custom_fields.
    """
    if not BOTCONVERSA_API_TOKEN:
        logger.warning("BOTCONVERSA_API_TOKEN não configurado; fetch_contact será limitado.")
        return {}

    if contact_id:
        url = f"{BOTCONVERSA_API_BASE}/contacts/{contact_id}"
        resp = _safe_request("GET", url, headers=_get_headers())
        if resp is None:
            return {}
        try:
            data = resp.json()
        except Exception:
            logger.warning("Falha ao decodificar JSON de contato (id=%s)", contact_id)
            return {}
        return _normalize_contact_payload(data)

    # Fallback por telefone (se a API suportar /contacts?phone=)
    if phone:
        url = f"{BOTCONVERSA_API_BASE}/contacts"
        params = {"phone": phone}
        resp = _safe_request("GET", url, headers=_get_headers(), params=params)
        if resp is None:
            return {}
        try:
            payload = resp.json()
        except Exception:
            logger.warning("Falha ao decodificar JSON de busca por telefone (%s)", phone)
            return {}

        # Dependendo da API, pode vir em "results" ou lista directa
        if isinstance(payload, dict) and "results" in payload:
            results = payload["results"]
        else:
            results = payload

        if not results:
            return {}
        return _normalize_contact_payload(results[0])

    return {}


def _normalize_contact_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Tenta padronizar o payload de contato em um formato amigável para o Assistente."""
    name = raw.get("name") or raw.get("first_name") or raw.get("full_name")
    phone = raw.get("phone") or raw.get("whatsapp_number")

    tags: List[str] = []
    raw_tags = raw.get("tags") or []
    if isinstance(raw_tags, list):
        for t in raw_tags:
            if isinstance(t, str):
                tags.append(t)
            elif isinstance(t, dict):
                # Ex.: {"id": 1, "name": "Lead Quente"}
                tag_name = t.get("name")
                if tag_name:
                    tags.append(tag_name)

    custom_fields = raw.get("custom_fields") or raw.get("fields") or {}

    return {
        "id": raw.get("id"),
        "name": name,
        "phone": phone,
        "tags": tags,
        "custom_fields": custom_fields,
        "raw": raw,
    }


# ---------------------------
# Ferramentas para Assistente
# ---------------------------


def tag_contact_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Função chamada pelo Assistente para etiquetar um contato.

    Espera algo como:
      {
        "contact_id": "123456",
        "tags": ["Polimento", "Lead Quente"]
      }

    Aqui está preparado para, no futuro, chamar a API real de tags.
    Por enquanto, loga a intenção e retorna um OK.
    """
    contact_id = str(args.get("contact_id") or "")
    tags: List[str] = list(args.get("tags") or [])

    # TODO: implementar chamada real à API de tags do BotConversa
    logger.info("[TAG] Etiquetando contato %s com tags: %s", contact_id, tags)

    return {
        "status": "ok",
        "contact_id": contact_id,
        "tags": tags,
        "note": "Tags registradas pelo middleware (pode evoluir para API real de tags).",
    }


def get_contact_context_tool(args:_
