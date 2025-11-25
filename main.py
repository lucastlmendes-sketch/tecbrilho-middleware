# main.py
from typing import Optional, Dict, Any

from fastapi import FastAPI
from pydantic import BaseModel

from openai_client import call_erika
from google_calendar import create_event_from_payload, CalendarError

app = FastAPI()


# Modelos para aceitar tanto { phone, message } quanto { root: { ... } }
class RootPayload(BaseModel):
    phone: Optional[str] = None
    message: Optional[str] = None
    thread_id: Optional[str] = None


class WebhookPayload(BaseModel):
    root: Optional[RootPayload] = None
    phone: Optional[str] = None
    message: Optional[str] = None
    thread_id: Optional[str] = None


def _normalize_payload(payload: WebhookPayload) -> RootPayload:
    if payload.root is not None:
        return payload.root

    return RootPayload(
        phone=payload.phone,
        message=payload.message,
        thread_id=payload.thread_id,
    )


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook_chat")
def webhook_chat(payload: WebhookPayload) -> Dict[str, Any]:
    data = _normalize_payload(payload)

    if not data.phone or not data.message:
        return {
            "send": [
                {
                    "type": "text",
                    "value": "Tive um probleminha técnico aqui agora, mas já podemos tentar de novo em instantes, tudo bem? 🙏",
                }
            ],
            "variables": {
                "erro_interno": "Payload inválido: faltando phone ou message.",
            },
        }

    # Chama a Erika via OpenAI
    erika_result = call_erika(phone=data.phone, message=data.message)

    reply_text: str = erika_result["reply"]
    thread_id: str = erika_result["thread_id"]
    calendar_payload = erika_result.get("calendar_payload")

    variables: Dict[str, Any] = {
        "erika_resposta": reply_text,
        "thread_id": thread_id,
    }

    # Se tiver instrução de agenda, tenta criar o evento
    if calendar_payload:
        try:
            event = create_event_from_payload(calendar_payload, phone=data.phone)
            variables["calendar_event_id"] = event.get("id")
        except CalendarError as ce:
            variables["calendar_error"] = f"CalendarError: {ce}"
        except Exception as e:
            variables["calendar_error"] = f"Erro inesperado ao criar evento: {e}"

    return {
        "send": [
            {
                "type": "text",
                "value": reply_text,
            }
        ],
        "variables": variables,
    }
