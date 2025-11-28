from fastapi import FastAPI, Request
from pydantic import BaseModel
from openai import OpenAI
from calendar_client import GoogleCalendarClient
import os

app = FastAPI()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
calendar_client = GoogleCalendarClient()

OPENAI_AGENDA_ASSISTANT_ID = os.getenv("OPENAI_AGENDA_ASSISTANT_ID")

# --------------------------
# MODELO DE PAYLOAD DO BOTCONVERSA
# --------------------------
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


# --------------------------
# ROTA DO WEBHOOK
# --------------------------
@app.post("/agenda-webhook")
async def agenda_webhook(payload: AgendaPayload):

    # 1. Criar nova thread para enviar ao Assistente de Agenda
    thread = client.beta.threads.create()

    # 2. Enviar mensagem ao assistente Agenda
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=f"""
        Faça o agendamento no Google Agenda com os seguintes dados:

        • Nome: {payload.nome}
        • Telefone: {payload.telefone}
        • Carro: {payload.carro}
        • Serviço: {payload.servicos}
        • Categoria do serviço: {payload.categoria}
        • Data: {payload.data}
        • Horário: {payload.hora}
        • Duração (minutos): {payload.duracao}
        • Histórico: {payload.historico}

        Gere uma mensagem curta de confirmação para enviar ao cliente.
        """
    )

    # 3. Rodar o assistente
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=OPENAI_AGENDA_ASSISTANT_ID
    )

    # 4. Esperar terminar
    from time import sleep
    while True:
        check = client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id
        )
        if check.status == "completed":
            break
        sleep(1)

    # 5. Buscar resposta
    messages = client.beta.threads.messages.list(thread_id=thread.id)
    resposta = messages.data[0].content[0].text.value

    return {
        "ok": True,
        "msg": resposta
    }
