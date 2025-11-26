import logging
import os
from typing import List, Dict, Any, Optional

import httpx

logger = logging.getLogger(__name__)

BOTCONVERSA_API_BASE = os.getenv("BOTCONVERSA_API_BASE", "https://backend.botconversa.com.br/api/v1")
BOTCONVERSA_API_TOKEN = os.getenv("BOTCONVERSA_API_TOKEN", "")


def _headers() -> Dict[str, str]:
    if not BOTCONVERSA_API_TOKEN:
        raise RuntimeError("BOTCONVERSA_API_TOKEN não configurado.")
    return {
        "Authorization": f"Token {BOTCONVERSA_API_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }


def _safe_request(method: str, url: str, **kwargs) -> Optional[httpx.Response]:
    try:
        with httpx.Client(timeout=10) as client:
            r = client.request(method, url, **kwargs)
        if r.status_code >= 400:
            logger.warning("Erro BotConversa %s %s -> %s %s", method, url, r.status_code, r.text)
            return None
        return r
    except Exception as exc:
        logger.exception("Falha HTTP: %s", exc)
        return None


def fetch_contact(contact_id: Optional[str], phone: Optional[str]) -> Dict[str, Any]:
    if not BOTCONVERSA_API_TOKEN:
        logger.warning("Token BC ausente; fetch_contact será limitado.")
        return {}

    # 1) Buscar por contact_id
    if contact_id:
        url = f"{BOTCONVERSA_API_BASE}/contacts/{contact_id}"
        r = _safe_request("GET", url, headers=_headers())
        if r:
            try:
                return _normalize(r.json())
            except:
                pass

    # 2) Buscar por telefone (fallback)
    if phone:
        url = f"{BOTCONVERSA_API_BASE}/contacts"
        r = _safe_request("GET", url, headers=_headers(), params={"phone": phone})
        if r:
            try:
                data = r.json()
            except:
                return {}

            results = data.get("results") or data
            if results:
                return _normalize(results[0])

    return {}


def _normalize(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normaliza payload do BotConversa.
    """

    # Tags
    tags_raw = raw.get("tags") or []
    tags = []
    for t in tags_raw:
        if isinstance(t, str):
            tags.append(t)
        elif isinstance(t, dict):
            name = t.get("name")
            if name:
                tags.append(name)

    return {
        "id": raw.get("id"),
        "name": raw.get("name") or raw.get("full_name"),
        "phone": raw.get("phone") or raw.get("whatsapp_number"),
        "custom_fields": raw.get("custom_fields") or {},
        "tags": tags,
    }


# Ferramentas strict mode

def tag_contact_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Compatível com strict mode: recebe sempre contact_id e tags."""
    cid = args.get("contact_id")
    tags = args.get("tags") or []

    if not cid or not isinstance(tags, list):
        return {"error": "Parâmetros inválidos para tag_contact."}

    logger.info("[TAG_CONTACT] %s: %s", cid, tags)

    return {"status": "ok", "contact_id": cid, "tags": tags}


def get_contact_context_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    cid = args.get("contact_id")
    phone = args.get("phone")

    contact = fetch_contact(cid, phone)
    if not contact:
        return {"status": "not_found", "contact_id": cid, "phone": phone}

    return {
        "status": "ok",
        **contact
    }
