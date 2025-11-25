import os
import json
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from openai_client import OpenAIChatClient
from state_store import StateStore

app = FastAPI(title="TecBrilho Middleware", version="1.0.0")

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
    2. Usa contact_id como identificador único do cliente
       para manter o histórico da conversa no Assistente.
    3. Chama o Assistente da OpenAI.
    4. Devolve JSON no formato esperado pelo BotConversa:

       {
         "send": [
           {"type": "text", "value": "resposta da Erika"}
         ],
         "variables": {
           "erika_resposta": "resposta da Erika",
           "contact_thread_id": "thread_xxx"
         }
       }

    Depois, no BotConversa, você pode:
      - Mapear send[0].value para um campo de robô (ex: erika_resposta)
      - Mapear contact_thread_id para outro campo se quiser
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

    contact_id = request_obj.contact_id or request_obj.phone

    try:
        reply_text, thread_id = await chat_client.handle_message(
            contact_id=contact_id,
            phone=request_obj.phone,
            message=request_obj.message,
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
        },
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
