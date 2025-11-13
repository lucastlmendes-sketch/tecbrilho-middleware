import os
import json
import datetime
from typing import Optional, Tuple, Dict, Any
from urllib.parse import parse_qs

import re
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
ERIKA_ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID") or ""

ACTION_START = "### ERIKA_ACTION"
ACTION_END = "### END_ERIKA_ACTION"


def log(*args):
    print(datetime.datetime.now().isoformat(), "-", *args, flush=True)


# =========================================
# EXTRATOR DE TELEFONE UNIVERSAL — 360°
# =========================================

def extract_phone_intelligent(payload: dict) -> Optional[str]:
    """
    Extrator robusto que vasculha o payload inteiro do Kommo
    e encontra qualquer formato de telefone.
    """
    try:
        as_text = json.dumps(payload, ensure_ascii=False)
    except Exception:
        as_text = str(payload)

    # 1 — Buscar formato internacional padrão
    matches = re.findall(r"\+?\d{11,15}", as_text)
    if matches:
        return max(matches, key=len)  # pega o maior número (normalmente o telefone real)

    # 2 — Detecta formato WABA
    waba = re.search(r"waba:\+?\d{11,15}", as_text)
    if waba:
        return waba.group().replace("waba:", "")

    # 3 — Busca campos explícitos no dict
    possible_keys = ["phone", "telefone", "mobile", "value", "tel"]

    def deep_search(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if any(pk in k.lower() for pk in possible_keys):
                    if isinstance(v, str) and re.search(r"\+?\d{11,15}", v):
                        return v
                result = deep_search(v)
                if result:
                    return result
        elif isinstance(obj, list):
            for i in obj:
                result = deep_search(i)
                if result:
                    return result
        return None

    candidate = deep_search(payload)
    if candidate:
        candidate = re.sub(r"[^\d+]", "", candidate)
        # normaliza pro padrão +55...
        if not candidate.startswith("+"):
            if candidate.startswith("55"):
                candidate = "+" + candidate
            else:
                candidate = "+55" + candidate
        return candidate

    return None


# =========================================
# Rotas básicas
# =========================================

@app.get("/")
async def root():
    return {"status": "ok", "message": "kommo-middleware online"}


@app.get("/health")
async def health():
    return {"status": "ok"}


# =========================================
# Split ERIKA_ACTION
# =========================================

def split_erika_output(full: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Separa o texto visível ao cliente do bloco técnico ERIKA_ACTION.
    """
    if not full:
        return "", None

    start = full.rfind(ACTION_START)
    if start == -1:
        return full.strip(), None

    visible = full[:start].rstrip()
    after = full[start + len(ACTION_START):]
    end = after.rfind(ACTION_END)
    block = after[:end] if end != -1 else after
    block = block.strip()

    if not block:
        return visible, None

    try:
        parsed = json.loads(block)
    except Exception:
        log("Erro ao parsear ERIKA_ACTION:", block[:300])
        return visible, None

    return visible, parsed


# =========================================
# Helpers Kommo — notas e etapas
# =========================================

def add_kommo_note(lead_id: Optional[int], text: str):
    """
    Cria uma nota 'common' no lead do Kommo.
    """
    if not lead_id or not KOMMO_TOKEN or not KOMMO_DOMAIN or not text:
        return

    url = f"{KOMMO_DOMAIN}/api/v4/leads/notes"
    payload = [{
        "entity_id": int(lead_id),
        "note_type": "common",
        "params": {"text": text}
    }]

    headers = {"Authorization": f"Bearer {KOMMO_TOKEN}"}

    log("-> Enviando nota ao Kommo:", text[:80].replace("\n", " "), "...")
    try:
        requests.post(url, headers=headers, json=payload, timeout=20)
    except Exception as e:
        log("Erro ao enviar nota:", repr(e))


# Mapeamento de nome da etapa -> variável de ambiente com o status_id do Kommo
STAGE_ENV_MAP = {
    "Leads Recebidos": "KOMMO_STATUS_LEADS_RECEBIDOS",
    "Contato em Andamento": "KOMMO_STATUS_CONTATO_EM_ANDAMENTO",
    "Serviço Vendido": "KOMMO_STATUS_SERVICO_VENDIDO",
    "Agendamento Pendente": "KOMMO_STATUS_AGENDAMENTO_PENDENTE",
    "Agendamentos Confirmados": "KOMMO_STATUS_AGENDAMENTOS_CONFIRMADOS",
    "Cliente Presente": "KOMMO_STATUS_CLIENTE_PRESENTE",
    "Cliente Ausente": "KOMMO_STATUS_CLIENTE_AUSENTE",
    "Reengajar": "KOMMO_STATUS_REENGAJAR",
    "Solicitar FeedBack": "KOMMO_STATUS_SOLICITAR_FEEDBACK",
    "Solicitar Avaliação Google": "KOMMO_STATUS_SOLICITAR_AVALIACAO_GOOGLE",
    "Avaliação 5 Estrelas": "KOMMO_STATUS_AVALIACAO_5_ESTRELAS",
    "Cliente Insatisfeito": "KOMMO_STATUS_CLIENTE_INSATISFEITO",
    "Vagas de Emprego": "KOMMO_STATUS_VAGAS_DE_EMPREGO",
    "Solicitar Atendimento Humano": "KOMMO_STATUS_SOLICITAR_ATENDIMENTO_HUMANO",
}


def update_lead_stage(lead_id: Optional[int], stage_name: Optional[str]):
    """
    Atualiza a etapa/status do lead no Kommo,
    usando as variáveis de ambiente KOMMO_STATUS_*.
    """
    if not lead_id or not stage_name:
        return

    env_name = STAGE_ENV_MAP.get(stage_name)
    if not env_name:
        log("Nenhum env configurado para etapa:", stage_name)
        return

    status_id = os.getenv(env_name)
    if not status_id:
        log("Variável de ambiente não definida para", stage_name, "=>", env_name)
        return

    if not KOMMO_DOMAIN or not KOMMO_TOKEN:
        log("KOMMO_DOMAIN ou KOMMO_TOKEN não configurados, não foi possível mover o lead.")
        return

    url = f"{KOMMO_DOMAIN}/api/v4/leads/{int(lead_id)}"
    payload = {"status_id": int(status_id)}
    headers = {"Authorization": f"Bearer {KOMMO_TOKEN}"}

    log(f"-> Atualizando lead {lead_id} para etapa '{stage_name}' (status_id={status_id})")
    try:
        requests.patch(url, headers=headers, json=payload, timeout=20)
    except Exception as e:
        log("Erro ao atualizar etapa do lead:", repr(e))


# =========================================
# Parser de Webhook form-urlencoded
# =========================================

def parse_kommo_form_urlencoded(body: bytes) -> Dict[str, Any]:
    text = body.decode("utf-8", "ignore")
    qs = parse_qs(text)

    def first(key):
        vals = qs.get(key)
        return vals[0] if vals else None

    def safe_int(v):
        try:
            return int(v)
        except Exception:
            return None

    message_text = (
        first("message[text]") or
        first("message[body]") or
        first("message[message]") or
        first("message[add][0][text]")
    )

    lead_id = safe_int(
        first("lead[id]") or
        first("leads[0][id]") or
        first("message[add][0][entity_id]")
    )

    phone = (
        first("contact[phones][0][value]") or
        first("contact[phone]") or
        first("phone")
    )

    payload = {
        "account": {"subdomain": first("account[subdomain]")},
        "data": {
            "message": {"text": message_text} if message_text else {},
            "lead": {"id": lead_id} if lead_id else {},
            "contact": {"phones": [{"value": phone}]} if phone else {}
        }
    }

    return payload


# =========================================
# ERIKA (OpenAI Assistant)
# =========================================

def call_openai_erika(user_message: str, lead_id=None, phone=None) -> str:
    if not ERIKA_ASSISTANT_ID:
        raise RuntimeError("OPENAI_ASSISTANT_ID não configurado")

    meta = []
    if lead_id:
        meta.append(f"lead_id={lead_id}")
    if phone:
        meta.append(f"telefone={phone}")

    msgs = [{"role": "user", "content": user_message}]
    if meta:
        msgs.append({"role": "user", "content": "[CONTEXTO KOMMO] " + " | ".join(meta)})

    log("-> Criando thread Erika (lead_id=", lead_id, ", phone=", phone, ")")

    thread = client.beta.threads.create(messages=msgs)
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id,
        assistant_id=ERIKA_ASSISTANT_ID
    )

    if run.status != "completed":
        log("Run Erika não completou. status=", run.status)
        return ""

    messages = client.beta.threads.messages.list(thread_id=thread.id, limit=10)

    for m in messages.data:
        if m.role == "assistant":
            out = "\n".join(
                part.text.value
                for part in m.content
                if part.type == "text"
            )
            log("-> Resposta Erika (preview):", out[:120].replace("\n", " "), "...")
            return out

    return ""


# =========================================
# WEBHOOK PRINCIPAL
# =========================================

@app.post("/kommo-webhook")
async def kommo_webhook(request: Request):
    raw = await request.body()
    log("RAW (200b):", raw[:200])

    content_type = (request.headers.get("content-type") or "").lower()

    try:
        if "json" in content_type:
            payload = json.loads(raw.decode("utf-8"))
        else:
            payload = parse_kommo_form_urlencoded(raw)
    except Exception as e:
        log("Erro ao interpretar payload:", repr(e))
        raise HTTPException(400, "Payload inválido")

    log("Payload normalizado:", json.dumps(payload)[:800])

    data = payload.get("data") or payload
    message_block = data.get("message") or {}

    message_text = (
        message_block.get("text") or
        message_block.get("body") or
        message_block.get("message") or
        data.get("text") or ""
    )

    if not str(message_text).strip():
        log("Sem mensagem → ignorado")
        return {"status": "ignored", "reason": "sem mensagem"}

    lead = data.get("lead") or {}
    lead_id = lead.get("id") or data.get("lead_id")

    # 🌟 EXTRAÇÃO UNIVERSAL DE TELEFONE (contexto pra Erika)
    phone = extract_phone_intelligent(payload)
    log("📞 Telefone extraído:", phone)

    # Chama Erika
    ai_raw = call_openai_erika(message_text, lead_id=lead_id, phone=phone)
    visible, action = split_erika_output(ai_raw)

    reply = visible.strip() or "Oi! Sou a Erika da TecBrilho. Como posso ajudar?"

    # Cria nota e movimenta funil se tiver ERIKA_ACTION
    if lead_id:
        add_kommo_note(lead_id, f"Erika 🧠:\n{reply}")

        if action and isinstance(action, dict):
            # nota-resumo opcional
            summary = action.get("summary_note")
            if summary:
                add_kommo_note(lead_id, f"ERIKA_ACTION: {summary}")

            # sugestão de etapa
            stage = action.get("kommo_suggested_stage")
            if stage:
                update_lead_stage(lead_id, stage)

    # Esse retorno é só pra debug (Kommo não usa pra WhatsApp)
    return {
        "status": "ok",
        "lead_id": lead_id,
        "phone": phone,
        "reply": reply,
        "erika_action": action,
    }
