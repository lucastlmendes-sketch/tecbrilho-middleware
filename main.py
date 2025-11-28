# main.py
"""
TecBrilho Middleware - Arquitetura A
-----------------------------------
Fluxo:
  BotConversa -> /agenda-webhook -> Assistente Agenda (OpenAI) -> Confirmação
"""

import os
import json
import logging
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from openai_client import openai_client

# ---------------------------------------
# LOGGING
# ---------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------
# APP FASTAPI
# ---------------------------------------
app = FastAPI(title="TecBrilho Middleware", version="2.0.0")

# CORS liberado (seguro e necessário para BotConversa)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------
# Modelo do payload enviado pelo BotConversa
# ---------------------------------------
class AgendaPayload(BaseModel):
    data: str
    hora: str
    nome: str
    carro: str
    duracao: str
    servicos: str
    telefone: str
    categoria: str
    historico: str


# ---------------------------------------
# Healthcheck (GET + HEAD)
# ---------------------------------------
@app.api_route("/", methods=["GET", "HEAD"])
async def health() -> Dict[str, Any]:
    """
    Healthcheck compatível com Render (aceita GET e HEAD).
    """
    return {
        "status": "ok",
        "version": app.version,
        "timezone": settings.timezone,
    }


# ---------------------------------------
# ROTA PRINCIPAL - WEBHOOK
# ---------------------------------------
@app.post("/agenda-webhook")
async def agenda_webhook(payload: AgendaPayload):
    """
    Webhook chamado pelo BotConversa.
    Envia os dados ao Assistente Erika Agenda e retorna
    mensagem pronta para o cliente.
    """

    logger.info("[WEBHOOK] Dados recebidos: %s", payload.json(ensure_ascii=False))

    # ---------------------------------------
    # Montar prompt para o Assistente Agenda
    # ---------------------------------------
    prompt = f"""
    Faça o agendamento no Google Agenda com as seguintes informações:

    • Nome do cliente: {payload.nome}
    • Telefone: {payload.telefone}
    • Modelo do veículo: {payload.carro}
    • Serviço escolhido: {payload.servicos}
    • Categoria: {payload.categoria}
    • Data desejada: {payload.data}
    • Horário desejado: {payload.hora}
    • Duração (minutos): {payload.duracao}

    Histórico da conversa:
    {payload.historico}

    Instruções:
    - Valide disponibilidade automaticamente.
    - Crie o evento no calendário configurado.
    - Gere uma mensagem curta, amigável e profissional confirmando o agendamento.
    """

    # ---------------------------------------
    # Processar no Assistente Agenda
    # ---------------------------------------
    try:
        mensagem_final = openai_client.process_agendamento(prompt)
    except Exception as exc:
        logger.exception("Erro ao processar Assistente Agenda: %s", exc)
        mensagem_final = (
            "Tive um problema para confirmar seu agendamento agora. "
            "Pode tentar novamente em alguns instantes ou falar com a equipe TecBrilho."
        )

    # ---------------------------------------
    # Resposta no formato do BotConversa
    # ---------------------------------------
    resposta = {
        "send": [
            {
                "type": "text",
                "value": mensagem_final
            }
        ]
    }

    logger.info("[WEBHOOK] Resposta enviada ao BotConversa: %s", mensagem_final)

    return resposta


# ---------------------------------------
# Executar localmente (opcional)
# ---------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
