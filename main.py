import json
import logging
import os
import time
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

from config import settings
from calendar_client import GoogleCalendarClient


# ------------------------------------------------------------------------------
# Configuração básica
# ------------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tecbrilho-middleware")

app = FastAPI(title="TecBrilho Middleware", version="2.0.0")

# CORS liberado – o BotConversa não exige, mas isso não atrapalha
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Clientes globais
openai_client = OpenAI(api_key=settings.openai_api_key)
calendar_client = GoogleCalendarClient()
OPENAI_AGENDA_ASSISTANT_ID = os.getenv("OPENAI_AGENDA_ASSISTANT_ID", "").strip()


# ------------------------------------------------------------------------------
# Modelos
# ------------------------------------------------------------------------------
class AgendaPayload(BaseModel):
    """Formato que o BotConversa envia para o /agenda-webhook."""
    data: str        # data_agnd
    hora: str        # hora_agnd
    nome: str        # nome_cliente
    carro: str       # modelo_carro
    duracao: str     # durac_min (pode vir como texto, tratamos depois)
    servicos: str    # servicos_ctrd
    telefone: str    # tel_cliente
    categoria: str   # srv_calendar
    historico: str   # HistóricoConversas

    def to_description(self) -> str:
        """Gera um texto organizado para mandar para a Erika Agenda."""
        return (
            f"Nome: {self.nome}\n"
            f"Telefone: {self.telefone}\n"
            f"Carro: {self.carro}\n"
            f"Serviço(s): {self.servicos}\n"
            f"Categoria do serviço (calendário): {self.categoria}\n"
            f"Data desejada: {self.data}\n"
            f"Horário desejado: {self.hora}\n"
            f"Duração aproximada (minutos): {self.duracao}\n"
            f"Resumo / histórico da conversa:\n{self.historico}"
        )


# ------------------------------------------------------------------------------
# Healthcheck
# ------------------------------------------------------------------------------
@app.get("/")
async def healthcheck() -> Dict[str, Any]:
    return {
        "status": "ok",
        "version": app.version,
        "timezone": settings.timezone,
    }


# ------------------------------------------------------------------------------
# Função auxiliar: roda o Assistente de Agenda com ferramenta create_calendar_event
# ------------------------------------------------------------------------------
def run_agenda_assistant(payload: AgendaPayload) -> str:
    """
    Cria uma thread, envia os dados do agendamento para o assistente de Agenda
    (OPENAI_AGENDA_ASSISTANT_ID) e processa as chamadas de ferramenta
    create_calendar_event, usando o GoogleCalendarClient.

    Retorna apenas a mensagem final de confirmação para o cliente.
    """
    if not OPENAI_AGENDA_ASSISTANT_ID:
        raise RuntimeError("OPENAI_AGENDA_ASSISTANT_ID não configurado no ambiente.")

    # 1. Criar thread
    thread = openai_client.beta.threads.create()
    logger.info("Thread de agenda criada: %s", thread.id)

    # 2. Enviar mensagem inicial para a Erika Agenda
    content = (
        "Você é a Erika Agenda, responsável apenas por criar eventos no Google "
        "Agenda usando a ferramenta create_calendar_event.\n\n"
        "Use SEMPRE essa ferramenta quando o cliente confirmar um agendamento. "
        "Os dados do agendamento são:\n\n"
        f"{payload.to_description()}\n\n"
        "Regras importantes:\n"
        "- Interprete a data e o horário informados (ex.: 'amanhã às 9h').\n"
        "- Converta para ISO 8601 considerando o fuso horário "
        f"{settings.timezone}.\n"
        "- Use o campo 'categoria' para decidir o service_type correto "
        "(polimentos, higienizacao, lavagens, peliculas, instalacoes, "
        "martelinho, role_guarulhos). Se não tiver certeza, use 'default'.\n"
        "- No título do evento inclua o primeiro nome do cliente e o serviço "
        "principal (ex.: 'Lucas – Polimento Técnico').\n"
        "- Na descrição inclua telefone, modelo do carro, serviços contratados "
        "e um mini-resumo do combinado.\n\n"
        "Depois que o evento for criado com sucesso, responda APENAS com uma "
        "mensagem curta e amigável de confirmação em português, própria para "
        "enviar no WhatsApp."
    )

    openai_client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=content,
    )

    # 3. Iniciar execução do assistente
    run = openai_client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=OPENAI_AGENDA_ASSISTANT_ID,
    )
    logger.info("Run de agenda iniciado: %s", run.id)

    # 4. Loop até completar ou falhar
    while True:
        run_status = openai_client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id,
        )
        status = run_status.status
        logger.info("Status atual do run %s: %s", run.id, status)

        if status == "requires_action":
            # O assistente quer chamar ferramentas (ex.: create_calendar_event)
            tool_outputs = []

            required = run_status.required_action.submit_tool_outputs
            for tool_call in required.tool_calls:
                if tool_call.type != "function":
                    continue

                function = tool_call.function
                logger.info("Tool call recebida: %s", function.name)

                if function.name == "create_calendar_event":
                    try:
                        args = json.loads(function.arguments)
                    except json.JSONDecodeError:
                        logger.exception(
                            "Argumentos inválidos para create_calendar_event: %s",
                            function.arguments,
                        )
                        output = json.dumps(
                            {
                                "success": False,
                                "error": "Argumentos inválidos para create_calendar_event",
                            },
                            ensure_ascii=False,
                        )
                    else:
                        try:
                            result = calendar_client.create_calendar_event(args)
                            output = json.dumps(result, ensure_ascii=False)
                        except Exception as exc:
                            logger.exception("Erro ao criar evento no calendário: %s", exc)
                            output = json.dumps(
                                {
                                    "success": False,
                                    "error": f"Erro ao criar evento no calendário: {exc}",
                                },
                                ensure_ascii=False,
                            )

                    tool_outputs.append(
                        {
                            "tool_call_id": tool_call.id,
                            "output": output,
                        }
                    )

            # Enviar resultados das ferramentas de volta para o Assistente
            openai_client.beta.threads.runs.submit_tool_outputs(
                thread_id=thread.id,
                run_id=run.id,
                tool_outputs=tool_outputs,
            )

        elif status in ("queued", "in_progress", "cancelling"):
            time.sleep(1)

        elif status == "completed":
            break

        else:
            # failed, cancelled, expired...
            raise RuntimeError(f"Execução do assistente de agenda falhou: {status}")

    # 5. Buscar a última mensagem do assistente
    messages = openai_client.beta.threads.messages.list(
        thread_id=thread.id,
        order="desc",
        limit=5,
    )

    for message in messages.data:
        if message.role != "assistant":
            continue
        for item in message.content:
            if item.type == "text":
                texto = item.text.value.strip()
                if texto:
                    logger.info("Mensagem final da Erika Agenda: %s", texto)
                    return texto

    raise RuntimeError("Não foi possível obter uma mensagem de confirmação da Erika Agenda.")


# ------------------------------------------------------------------------------
# Webhook chamado pelo BotConversa
# ------------------------------------------------------------------------------
@app.post("/agenda-webhook")
async def agenda_webhook(payload: AgendaPayload) -> Dict[str, Any]:
    """
    Recebe os dados de agendamento do BotConversa, delega para o Assistente
    de Agenda (via run_agenda_assistant) e devolve uma mensagem de confirmação
    no formato esperado pelo BotConversa.
    """
    logger.info(
        "Payload recebido no /agenda-webhook: %s",
        payload.json(ensure_ascii=False),
    )

    try:
        msg_confirmacao = run_agenda_assistant(payload)
    except Exception as exc:
        logger.exception("Falha ao processar agendamento: %s", exc)
        # Mensagem de contingência para o cliente
        msg_confirmacao = (
            "Eu tentei registrar seu agendamento mas tive um probleminha técnico. "
            "O time TecBrilho vai conferir manualmente e te confirmar na sequência, "
            "tudo bem?"
        )

    # resposta no padrão BotConversa
    return {
        "send": [
            {
                "type": "text",
                "value": msg_confirmacao,
            }
        ]
    }


# ------------------------------------------------------------------------------
# Execução local
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
