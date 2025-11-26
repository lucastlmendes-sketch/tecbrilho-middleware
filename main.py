import os
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from openai_client import OpenAIChatClient
from state_store import StateStore
import botconversa_client

app = FastAPI(title="TecBrilho Middleware", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

state_store = StateStore()
chat_client = OpenAIChatClient(state_store=state_store)


class BotConversaWebhook(BaseModel):
    phone: str
    message: str
    contact_id: Optional[str] = None


@app.get("/")
def healthcheck():
    return {"status": "ok", "service": "tecbrilho-middleware"}


@app.post("/webhook_chat")
async def webhook_chat(payload: Dict[str, Any]):

    # Suporte ao formato { root: {...} }
    if "phone" in payload and "message" in payload:
        data = payload
    elif "root" in payload:
        data = payload["root"]
    else:
        raise HTTPException(400, "Payload inválido para BotConversa")

    try:
        req = BotConversaWebhook(**data)
    except Exception as exc:
        raise HTTPException(400, f"Erro ao validar payload: {exc}")

    cid = req.contact_id or req.phone

    # Buscar informações do BotConversa
    contact_info = {}
    contact_name = None
    try:
        contact_info = botconversa_client.fetch_contact(req.contact_id, req.phone) or {}
        contact_name = contact_info.get("name")
    except Exception:
        contact_info = {}

    try:
        reply, thread = await chat_client.handle_message(
            contact_id=cid,
            phone=req.phone,
            message=req.message,
            contact_name=contact_name,
            extra_context={"botconversa_contact": contact_info},
        )
    except Exception as exc:
        return {
            "send": [{"type": "text", "value": "Desculpe, tive um probleminha técnico. Pode repetir por favor? 🙏"}],
            "variables": {"erro_interno": str(exc)},
        }

    return {
        "send": [{"type": "text", "value": reply}],
        "variables": {
            "erika_resposta": reply,
            "contact_thread_id": thread,
            "contact_name": contact_name or "",
        },
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
