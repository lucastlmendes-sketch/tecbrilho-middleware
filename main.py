import os
import json
import logging
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from openai_client import OpenAIChatClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="TecBrilho Middleware", version="2.0.0")

# CORS (não é estritamente necessário para o BotConversa, mas não atrapalha)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

openai_client = OpenAIChatClient()


@app.get("/")
async def healthcheck() -> Dict[str, Any]:
    """Endpoint simples para checar se a API está de pé."""
    return {
        "status": "ok",
        "version": app.version,
        "timezone": settings.timezone,
    }


@app.post("/agenda-webhook")
async def agenda_webhook(request: Request) -> Dict[str, Any]:
    """Endpoint chamado pelo BotConversa para criar um agendamento.

    Espera um JSON no formato:

        {
          "nome": "...",
          "telefone": "...",
          "carro": "...",
          "servicos": "...",
          "categoria": "...",
          "data": "...",
          "hora": "...",
          "duracao": "...",
          "contact_id": "...",
          "historico": "..."
        }
    """
    try:
        body = await request.json()
    except Exception as exc:
        logger.exception("Falha ao ler JSON do webhook: %s", exc)
        raise HTTPException(status_code=400, detail="Corpo da requisição não é um JSON válido.")

    logger.info(
        "[WEBHOOK] Payload recebido do BotConversa: %s",
        json.dumps(body, ensure_ascii=False),
    )

    try:
        mensagem_confirmacao = openai_client.run_agenda_assistant(body)
    except Exception as exc:
        logger.exception("Erro ao processar agendamento via Erika Agenda: %s", exc)
        mensagem_confirmacao = (
            "Tive um problema para confirmar seu agendamento agora. "
            "Pode tentar novamente em alguns instantes ou falar com a equipe TecBrilho."
        )

    # Resposta no formato esperado pelo BotConversa
    return {
        "send": [
            {
                "type": "text",
                "value": mensagem_confirmacao,
            }
        ]
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
