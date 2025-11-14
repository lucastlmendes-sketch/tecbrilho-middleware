import os
import json
import datetime
from typing import Optional, Tuple, Dict, Any

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
AUTHORIZED_SUBDOMAIN = os.getenv("AUTHORIZED_SUBDOMAIN") or ""
ERIKA_ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID") or ""

ACTION_START = "### ERIKA_ACTION"
ACTION_END = "### END_ERIKA_ACTION"


def log(*args):
    """Log simples com timestamp (aparece nos logs do Render)."""
    print(datetime.datetime.now().isoformat(), "-", *args, flush=True)


# =========================================
# Mapeamento de etapas do funil -> variáveis de ambiente
# =========================================

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


# =========================================
# Helpers Kommo: notas e mudança de etapa
# =========================================

def add_kommo_note(lead_id: Optional[int], text: str):
    """Cria uma nota 'common' no lead do Kommo."""
    if not lead_id or not KOMMO_DOMAIN or not KOMMO_TOKEN or not text:
        return

    url = f"{KOMMO_DOMAIN}/api/v4/leads/notes"
    payload = [
        {
            "entity_id": int(lead_id),
            "note_type": "common",
            "params": {"text": text},
        }
    ]
    headers = {"Authorization": f"Bearer {KOMMO_TOKEN}"}

    log("-> Enviando nota ao Kommo:", url, "lead_id=", lead_id)
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
    except Exception as e:
        log("Erro ao enviar nota:", repr(e))


def update_lead_stage(lead_id: Optional[int], stage_name: Optional[str]):
    """
    Atualiza a etapa/status do lead no Kommo, se IDs estiverem configurados.
    stage_name deve bater com as chaves de STAGE_ENV_MAP.
    """
    if not lead_id or not stage_name:
        return

    env_name = STAGE_ENV_MAP.get(stage_name)
    if not env_name:
        log("Nenhuma env configurada para etapa:", stage_name)
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
        r = requests.patch(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
    except Exception as e:
        log("Erro ao atualizar etapa do lead:", repr(e))


# =========================================
# Split ERIKA_ACTION
# =========================================

def split_erika_output(full_text: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Separa o texto visível ao cliente do bloco técnico ERIKA_ACTION.
    Retorna (texto_visivel, action_dict_ou_None).
    """
    if not full_text:
        return "", None

    start = full_text.rfind(ACTION_START)
    if start == -1:
        return full_text.strip(), None

    visible_text = full_text[:start].rstrip()

    after = full_text[start + len(ACTION_START):]
    end = after.rfind(ACTION_END)
    if end != -1:
        action_raw = after[:end]
    else:
        action_raw = after

    action_raw = action_raw.strip()

    if not action_raw:
        return visible_text, None

    try:
        action_data = json.loads(action_raw)
    except json.JSONDecodeError as e:
        log("Erro ao decodificar ERIKA_ACTION:", repr(e), "conteúdo:", action_raw[:500])
        return visible_text, None

    return visible_text, action_data


# =========================================
# EXTRATOR DE TELEFONE UNIVERSAL — 360°
# =========================================

def extract_phone_intelligent(payload: dict) -> Optional[str]:
    """
    Extrator bem robusto que vasculha o payload inteiro do Kommo
    e encontra qualquer formato de telefone.
    """

    try:
        as_text = json.dumps(payload, ensure_ascii=False)
    except Exception:
        as_text = str(payload)

    matches = re.findall(r"\+?\d{11,15}", as_text)
    phone = max(matches, key=len) if matches else None

    if not phone:
        waba = re.search(r"waba:\+?\d{11,15}", as_text)
        if waba:
            phone = waba.group().replace("waba:", "")

    if not phone:
        possible_keys = ["phone", "telefone", "mobile", "value", "tel"]

        def deep_search(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if any(pk in k.lower() for pk in possible_keys):
                        if isinstance(v, str) and re.search(r"\+?\d{8,15}", v):
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
            phone = candidate

    if not phone:
        return None

    phone = re.sub(r"[^\d+]", "", phone)
    if not phone.startswith("+"):
        if phone.startswith("55") and len(phone) >= 12:
            phone = "+" + phone
        else:
            phone = "+55" + phone

    return phone


# =========================================
# Erika (Assistants API)
# =========================================

def call_openai_erika(
    user_message: str,
    lead_id: Optional[int] = None,
    phone: Optional[str] = None
) -> str:
    """
    Chama a Erika via Assistants API usando o ID configurado em OPENAI_ASSISTANT_ID.
    Retorna o texto bruto da resposta da assistente (incluindo o bloco ERIKA_ACTION).
    """
    if not ERIKA_ASSISTANT_ID:
        raise RuntimeError("OPENAI_ASSISTANT_ID (ID da Erika) não configurado nas variáveis de ambiente.")

    meta_parts = []
    if lead_id:
        meta_parts.append(f"lead_id={lead_id}")
    if phone:
        meta_parts.append(f"telefone={phone}")

    meta_text = ""
    if meta_parts:
        meta_text = "[CONTEXTO KOMMO] " + " | ".join(meta_parts)

    messages = [{"role": "user", "content": user_message}]
    if meta_text:
        messages.append({"role": "user", "content": meta_text})

    log("-> Criando thread para Erika - lead_id:", lead_id, "phone:", phone)

    thread = client.beta.threads.create(messages=messages)

    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id,
        assistant_id=ERIKA_ASSISTANT_ID,
    )

    log("Status do run da Erika:", run.status)

    if run.status != "completed":
        raise RuntimeError(f"Execução da Erika não completou corretamente. status={run.status}")

    msgs = client.beta.threads.messages.list(thread_id=thread.id, limit=10)

    for msg in msgs.data:
        if msg.role == "assistant":
            texts = []
            for part in msg.content:
                if part.type == "text":
                    texts.append(part.text.value)
            if texts:
                resposta = "\n\n".join(texts)
                log("Resposta bruta da Erika (primeiros 400 chars):", resposta[:400])
                return resposta

    log("Nenhuma mensagem de assistente encontrada na thread da Erika.")
    return ""


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
# Endpoint usado pelo Chatbot Privado (SalesBot + Widget)
# =========================================

@app.post("/erika-chat")
async def erika_chat(request: Request):
    """
    Endpoint chamado pelo widget privado do Kommo (SalesBot).
    Espera um JSON com:
        {
            "message": "...",
            "lead_id": "123",
            "contact_name": "...",
            "contact_phone": "+55..."
        }
    Retorna:
        {
            "status": "success" | "error",
            "reply": "mensagem para o cliente"
        }
    O SalesBot usa "reply" para responder no WhatsApp.
    """
    try:
        body = await request.json()
    except Exception as e:
        log("Erro ao ler JSON em /erika-chat:", repr(e))
        raise HTTPException(status_code=400, detail="JSON inválido")

    log("Payload recebido em /erika-chat:", json.dumps(body)[:1000])

    # Validação opcional de subdomínio, se você decidir enviar isso no body
    if AUTHORIZED_SUBDOMAIN:
        account = body.get("account") or {}
        subdomain = account.get("subdomain") if isinstance(account, dict) else None
        if subdomain and subdomain != AUTHORIZED_SUBDOMAIN:
            log("Subdomínio não autorizado em /erika-chat:", subdomain)
            raise HTTPException(status_code=401, detail=f"Subdomínio não autorizado: {subdomain}")

    message = (body.get("message") or "").strip()
    if not message:
        log("Sem 'message' em /erika-chat → ignorado")
        raise HTTPException(status_code=400, detail="Campo 'message' é obrigatório")

    lead_id_raw = body.get("lead_id")
    try:
        lead_id = int(lead_id_raw) if lead_id_raw is not None else None
    except (TypeError, ValueError):
        lead_id = None

    phone = body.get("contact_phone") or body.get("phone")
    if not phone:
        phone = extract_phone_intelligent(body)

    try:
        ai_full = call_openai_erika(message, lead_id=lead_id, phone=phone)
    except Exception as e:
        log("Erro ao chamar Erika em /erika-chat:", repr(e))
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "reply": "Desculpe, tive um problema para responder agora. Tente novamente em instantes."
            },
        )

    visible_text, action = split_erika_output(ai_full)

    reply_text = (
        visible_text.strip()
        if visible_text and visible_text.strip()
        else "Oi! Sou a Erika, da TecBrilho. Como posso te ajudar hoje?"
    )

    # 🎯 AQUI ESTÁ SUA REGRA NOVA:
    # NÃO registramos a resposta completa em nota.
    # Apenas usamos o bloco ERIKA_ACTION (summary_note, kommo_suggested_stage, etc.).
    if lead_id and action and isinstance(action, dict):
        try:
            summary = action.get("summary_note")
            if summary:
                add_kommo_note(lead_id, summary)

            stage = action.get("kommo_suggested_stage")
            if stage:
                update_lead_stage(lead_id, stage)
        except Exception as e:
            log("Erro ao registrar notas/etapa em /erika-chat:", repr(e))

    return JSONResponse(
        {
            "status": "success",
            "reply": reply_text,
        }
    )
