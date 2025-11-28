# main.py
"""
TecBrilho Middleware - Arquitetura A (Assistente Agenda faz tudo)
-----------------------------------------------------------------
Fluxo:
  BotConversa -> /agenda-webhook -> Assistente Agenda (OpenAI) -> Google Calendar -> Mensagem final
"""

import logging
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any

from config import settings
from openai_client import openai_client


# ------------------------------------------------------
# LOGGING
# ------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TecBrilhoMiddleware")


# ------------------------------------------------------
# APP FASTAPI
# ------------------------------------------------------
app = FastAPI(
    title="TecBrilho Middleware",
    version="2.0.0",
    description="Middleware oficial TecBrilho — BotConversa + OpenAI + Google Calendar"
)

# CORS liberado (obrigatório para BotConversa)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------
# MODELO DE PAYLOAD DO BOTCONVERSA
# ------------------------------------------------------
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


# ------------------------------------------------------
# HEALTHCHECK (Render usa para saber se app está vivo)
# ------------------------------------------------------
@app.get("/")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "version": app.version,
        "calendar_id": settings.google_calendar_id,
        "timezone": settings.timezone,
        "assistant_agenda": settings.openai_agenda_assistant_id
    }


# ------------------------------------------------------
# ROTA PRINCIPAL - WEBHOOK DO BOTCONVERSA
# ------------------------------------------------------
@app.post("/agenda-webhook")
async def agenda_webhook(payload: AgendaPayload):
    """
    Webhook chamado pelo BotConversa.
    Aqui enviamos os dados para o Assistente Erika Agenda (OpenAI),
    que cria o evento no Google Calendar e devolve a mensagem final.
    """

    logger.info("📩 [WEBHOOK] Payload recebido:")
    logger.info(payload.model_dump())

    # Construir prompt para o assistente
    prompt = f"""
    Você é a assistente Erika Agenda.
    Sua tarefa é AGENDAR o serviço solicitado no Google Calendar.

    Dados completos do cliente:

    • Nome: {payload.nome}
    • Telefone: {payload.telefone}
    • Carro: {payload.carro}
    • Serviço(s): {payload.servicos}
    • Categoria: {payload.categoria}

    Agendamento solicitado:
    • Data: {payload.data}
    • Horário: {payload.hora}
    • Duração (min): {payload.duracao}

    Histórico da conversa:
    {payload.historico}

    Tarefas obrigatórias:
    1. Validar o horário no Google Calendar.
    2. Criar o evento no ID:
       {settings.google_calendar_id}
    3. Gerar uma mensagem final, educada e curta, confirmando o agendamento.
    """

    # CHAMAR ASSISTENTE E PROCESSAR
    try:
        mensagem_final = openai_client.process_agendamento(prompt)
    except Exception as exc:
        logger.exception("❌ Erro ao processar agendamento:")
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao processar agendamento."
        ) from exc

    logger.info("📤 [WEBHOOK] Mensagem retornada ao BotConversa:")
    logger.info(mensagem_final)

    # Resposta que o BotConversa espera
    return {
        "send": [
            {
                "type": "text",
                "value": mensagem_final
            }
        ]
    }


# ------------------------------------------------------
# EXECUTAR LOCALMENTE
# ------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
