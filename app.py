import os
import json
import datetime
from typing import Optional, Tuple, Dict, Any

from urllib.parse import parse_qs

import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from openai import OpenAI

# =========================================
# Configurações básicas
# =========================================

app = FastAPI()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

KOMMO_DOMAIN = (os.getenv("KOMMO_DOMAIN") or "").rstrip("/")
KOMMO_TOKEN = os.getenv("KOMMO_TOKEN") or ""
AUTHORIZED_SUBDOMAIN = os.getenv("AUTHORIZED_SUBDOMAIN") or ""
ERIKA_ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID") or ""

ACTION_START = "### ERIKA_ACTION"
ACTION_END = "### END_ERIKA_ACTION"


def log(*args):
    """Log simples com timestamp (aparece nos logs do Render)."""
    print(datetime.datetime.now().isoformat(), "-", *args, flush=True)


# =========================================
# NOVO — PARSER ROBUSTO DE TELEFONE
# =========================================

def extract_phone_from_anything(data: Dict[str, Any]) -> Optional[str]:
    """
    Tenta extrair telefone de qualquer lugar do payload do Kommo.
    """
    phone = None

    # 1 — contact.phones
    contact = data.get("contact") or {}
    if isinstance(contact, dict):
        phones = contact.get("phones") or contact.get("phones[]") or []
        if isinstance(phones, list) and phones:
            p = phones[0]
            if isinstance(p, dict):
                phone = p.get("value") or p.get("phone")
            elif isinstance(p, str):
                phone = p

    # 2 — bloco message
    msg = data.get("message") or {}
    if isinstance(msg, dict):
        phone = phone or msg.get("phone") or msg.get("from")

    # 3 — busca bruta no JSON
    if not phone:
        flat = json.dumps(data)
        import re
        m = re.search(r"\+?\d{11,14}", flat)
        if m:
            phone = m.group(0)

    # 4 — sanitização
    if phone:
        phone = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not phone.startswith("+"):
            if len(phone) == 11:         # exemplo: 11999998888
                phone = "+55" + phone
            elif len(phone) == 13 and phone.startswith("55"):
                phone = "+" + phone

    return phone


# =========================================
# Rotas básicas (Render / Healthcheck)
# =========================================

@app.get("/")
async def root():
    return {"status": "ok", "message": "kommo-middleware online"}


@app.get("/health")
async def health():
    return {"status": "ok"}


# =========================================
# Helpers para ERIKA_ACTION
# =========================================

def split_erika_output(full_text: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    if not full_text:
        return "", None

    start = full_text.rfind(ACTION_START)
    if start == -1:
        return full_text.strip(), None

    visible_text = full_text[:start].rstrip()
    after = full_text[start + len(ACTION_START):]
    end = after.rfind(ACTION_END)
    action_raw = after[:end] if end != -1 else after
    action_raw = action_raw.strip()

    if not action_raw:
        return visible_text, None

    try:
        action_data = json.loads(action_raw)
    except json.JSONDecodeError as e:
        log("Erro ao decodificar ERIKA_ACTION:", repr(e))
        return visible_text, None

    return visible_text, action_data


# =========================================
# Helpers para Kommo (notas e etapas)
# =========================================

def add_kommo_note(lead_id: Optional[int], text: str):
    if not lead_id or not KOMMO_DOMAIN or not KOMMO_TOKEN or not text:
        return

    url = f"{KOMMO_DOMAIN}/api/v4/leads/notes"
    payload = [{
        "entity_id": int(lead_id),
        "note_type": "common",
        "params": {"text": text}
    }]
    headers = {"Authorization": f"Bearer {KOMMO_TOKEN}"}

    log("Enviando nota para Kommo:", url, "lead_id=", lead_id)
    requests.post(url, headers=headers, json=payload, timeout=30)


# =========================================
# Parser Kommo (inalterado)
# =========================================

def parse_kommo_form_urlencoded(body: bytes) -> Dict[str, Any]:
    text = body.decode("utf-8", "ignore")
    qs = parse_qs(text)

    def first(key, default=None):
        vals = qs.get(key)
        return vals[0] if vals else default

    def safe_int(v):
        try:
            return int(v)
        except:
            return None

    account = {"subdomain": first("account[subdomain]")}
    msg_text = (
        first("message[text]") or first("message[body]") or first("message[message]") or
        first("message[add][0][text]") or first("message[add][0][message]")
    )

    message = {}
    for k, vals in qs.items():
        if k.startswith("message[") and k.endswith("]"):
            inner = k[len("message["):-1]
            if vals:
                message[inner] = vals[0]

    if msg_text:
        message["text"] = msg_text

    lead_id = safe_int(
        first("lead[id]") or first("leads[0][id]") or
        first("message[add][0][entity_id]") or first("message[add][0][element_id]")
    )

    phone = (
        first("contact[phones][0][value]") or
        first("contact[phones][0][phone]") or
        first("contact[phone]") or
        first("phone")
    )

    payload = {
        "account": account,
        "data": {
            "message": message if message else None,
            "lead": {"id": lead_id} if lead_id else None,
            "contact": {"phones": [{"value": phone}]} if phone else None
        }
    }

    return payload


# =========================================
# Erika
# =========================================

def call_openai_erika(user_message: str, lead_id=None, phone=None):
    if not ERIKA_ASSISTANT_ID:
        raise RuntimeError("OPENAI_ASSISTANT_ID não configurado.")

    meta = []
    if lead_id:
        meta.append(f"lead_id={lead_id}")
    if phone:
        meta.append(f"telefone={phone}")

    messages = [{"role": "user", "content": user_message}]
    if meta:
        messages.append({"role": "user", "content": "[CONTEXTO KOMMO] " + " | ".join(meta)})

    thread = client.beta.threads.create(messages=messages)
    run = client.beta.threads.runs.create_and_poll(thread_id=thread.id, assistant_id=ERIKA_ASSISTANT_ID)

    msgs = client.beta.threads.messages.list(thread_id=thread.id, limit=10)
    for msg in msgs.data:
        if msg.role == "assistant":
            return "\n".join(part.text.value for part in msg.content if part.type == "text")

    return ""


# =========================================
# Webhook
# =========================================

@app.post("/kommo-webhook")
async def kommo_webhook(request: Request):
    raw = await request.body()
    log("Webhook - raw body:", raw[:200])

    content_type = (request.headers.get("content-type") or "").lower()

    try:
        if "json" in content_type:
            payload = json.loads(raw.decode("utf-8"))
        else:
            payload = parse_kommo_form_urlencoded(raw)
    except:
        raise HTTPException(400, "Payload inválido")

    log("Payload normalizado:", json.dumps(payload)[:800])

    data = payload.get("data") or payload
    msg_block = data.get("message") or {}

    message_text = (
        msg_block.get("text") or msg_block.get("body") or
        msg_block.get("message") or data.get("text") or ""
    )

    if not str(message_text).strip():
        log("Sem mensagem. Ignorando.")
        return {"status": "ignored"}

    lead = data.get("lead") or {}
    lead_id = lead.get("id") or data.get("lead_id")

    # 🔥 NOVO: extrair telefone em todas as possibilidades
    phone = extract_phone_from_anything(data)
    log("📞 Telefone extraído:", phone)

    # Chama Erika
    ai_raw = call_openai_erika(message_text, lead_id=lead_id, phone=phone)
    visible, action = split_erika_output(ai_raw)

    reply = visible.strip() or "Oi! Sou a Erika da TecBrilho. Como posso ajudar?"

    if lead_id:
        add_kommo_note(lead_id, f"Erika 🧠:\n{reply}")

    return {
        "status": "ok",
        "reply": reply,
        "lead_id": lead_id,
        "phone": phone,
        "action": action,
    }
