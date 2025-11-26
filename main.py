import os
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings  # noqa: F401  # garante que config é carregado
from openai_client import OpenAIChatClient
from state_store import StateStore
import botconversa_client

app = FastAPI(title="TecBrilho Middleware", version="1.1.0")

# CORS (não é estritamente necessário para o BotConversa, mas não atrapalha)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

state_store = StateStore()
chat_client = OpenAIChatClient(state_store=state_store)


class BotConversaWebhook(BaseModel):
    """Formato mínimo que vamos esperar do BotConversa.

    Recomendação para o *Corpo* do bloco de integração (JSON pronto):

    {
      "phone": "{{telefone}}",
      "message": "{{mensagem}}",
      "contact_id": "{{id}}"
    }

    Se você usar outro formato, ajuste aqui.
    """

    phone: str
    message: str
    contact_id: Optional[str] = None


@app.get("/")
def healthcheck() -> Dict[str, str]:
    return {"status": "ok", "service": "tecbrilho-middleware"}


@app.post("/webhook_chat")
async def webhook_chat(payload: Dict[str, Any]):
    """Endpoint chamado pelo bloco de integração do BotConversa.

    1. Lê phone, message, contact_id do body.
    2. Busca (quando possível) os dados do contato no BotConversa.
    3. Usa contact_id como identificador único do cliente
       para manter o histórico da conversa no Assistente.
    4. Chama o Assistente da OpenAI.
    5. Devolve JSON no formato esperado pelo BotConversa:

       {
         "send": [
           {"type": "text", "value": "resposta da Erika"}
         ],
         "variables": {
           "erika_resposta": "resposta da Erika",
           "contact_thread_id": "thread_xxx",
           "contact_name": "Nome vindo do BotConversa (se houver)"
         }
       }
    """

    # Se o usuário preferir enviar { "root": { ... } }, lidamos com isso também
    if "phone" in payload and "message" in payload:
        data = payload
    elif "root" in payload and isinstance(payload["root"], dict):
        data = payload["root"]
    else:
        raise HTTPException(status_code=400, detail="Payload inválido para BotConversa")

    try:
        request_obj = BotConversaWebhook(**data)
    except Exception as exc:  # pydantic ValidationError ou outro
        raise HTTPException(status_code=400, detail=f"Erro ao validar payload: {exc}") from exc

    # Definimos um identificador estável para o contato (id do BC, senão telefone)
    contact_id = request_obj.contact_id or request_obj.phone

    # Busca dados do contato no BotConversa (nome, custom_fields, tags, etc.)
    contact_name: Optional[str] = None
    botconversa_contact: Dict[str, Any] = {}

    if request_obj.contact_id:
        botconversa_contact = botconversa_client.fetch_contact(
            contact_id=request_obj.contact_id,
            phone=request_obj.phone,
        ) or {}
        contact_name = botconversa_contact.get("name") or None

    try:
        reply_text, thread_id = await chat_client.handle_message(
            contact_id=contact_id,
            phone=request_obj.phone,
            message=request_obj.message,
            contact_name=contact_name,
            extra_context={"botconversa_contact": botconversa_contact} if botconversa_contact else None,
        )
    except Exception as exc:
        # Em caso de erro, devolvemos uma mensagem amigável
        fallback_text = (
            "Tive um probleminha técnico aqui agora, mas já podemos tentar de novo em instantes, tudo bem? 🙏"
        )
        # Também devolvemos detalhes internos em 'variables' para debug (apenas para logs)
        return {
            "send": [
                {"type": "text", "value": fallback_text}
            ],
            "variables": {
                "erro_interno": f"{type(exc).__name__}: {exc}",
            },
        }

    # Resposta padrão de sucesso
    return {
        "send": [
            {
                "type": "text",
                "value": reply_text,
            }
        ],
        "variables": {
            "erika_resposta": reply_text,
            "contact_thread_id": thread_id,
            "contact_name": contact_name or "",
        },
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
