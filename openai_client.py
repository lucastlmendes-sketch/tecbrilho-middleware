# openai_client.py
import os
import time
import json
from typing import Dict, Any, Optional

from openai import OpenAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY não configurada.")
if not ASSISTANT_ID:
    raise RuntimeError("OPENAI_ASSISTANT_ID não configurado.")

client = OpenAI(api_key=OPENAI_API_KEY)

# Mapa simples em memória: telefone -> thread_id
PHONE_THREADS: Dict[str, str] = {}


def _get_or_create_thread(phone: str) -> str:
    thread_id = PHONE_THREADS.get(phone)
    if thread_id:
        return thread_id

    thread = client.beta.threads.create()
    PHONE_THREADS[phone] = thread.id
    return thread.id


def call_erika(phone: str, message: str) -> Dict[str, Any]:
    """
    Envia a mensagem do cliente para a Erika e retorna:
    {
      "reply": "...texto para o cliente...",
      "thread_id": "...",
      "calendar_payload": {...} or None
    }

    Se a Erika quiser agendar, ela deve incluir no final da resposta:
    ###CALENDAR: { ...json... }
    """
    thread_id = _get_or_create_thread(phone)

    # Cria mensagem do usuário
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=message,
    )

    # Roda a Erika
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID,
    )

    # Polling simples
    while True:
        run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if run.status in ("completed", "failed", "cancelled", "expired"):
            break
        time.sleep(0.8)

    if run.status != "completed":
        return {
            "reply": "Tive um probleminha técnico aqui agora, mas já podemos tentar de novo em instantes, tudo bem? 🙏",
            "thread_id": thread_id,
            "calendar_payload": None,
        }

    # Pega a última mensagem da Erika
    messages = client.beta.threads.messages.list(
        thread_id=thread_id,
        order="desc",
        limit=5,
    )

    assistant_text = ""
    for msg in messages.data:
        if msg.role == "assistant":
            parts = []
            for c in msg.content:
                if c.type == "text":
                    parts.append(c.text.value)
            assistant_text = "\n".join(parts).strip()
            if assistant_text:
                break

    if not assistant_text:
        assistant_text = "Desculpa, não consegui gerar uma resposta agora. Pode repetir, por favor? 🙏"

    # Procura marcador de agenda
    calendar_payload: Optional[Dict[str, Any]] = None
    marker = "###CALENDAR:"
    idx = assistant_text.find(marker)
    if idx != -1:
        text_part = assistant_text[:idx].strip()
        json_part = assistant_text[idx + len(marker):].strip()
        assistant_text = text_part or assistant_text

        try:
            calendar_payload = json.loads(json_part)
        except Exception:
            # Se a Erika mandar JSON cagado, só ignora a parte de agenda
            calendar_payload = None

    return {
        "reply": assistant_text,
        "thread_id": thread_id,
        "calendar_payload": calendar_payload,
    }
