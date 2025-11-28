import os
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel

from google.oauth2 import service_account
from googleapiclient.discovery import build

from openai import OpenAI

# ----------------------------
# Configurações via ENV
# ----------------------------

GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
GOOGLE_SERVICE_ACCOUNT_INFO = os.getenv("GOOGLE_SERVICE_ACCOUNT_INFO")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ASSISTANT_ID = os.getenv("OPENAI_AGENDA_ASSISTANT_ID")
TIMEZONE = os.getenv("TIMEZONE", "America/Sao_Paulo")

if not all([GOOGLE_CALENDAR_ID, GOOGLE_SERVICE_ACCOUNT_INFO, OPENAI_API_KEY, OPENAI_ASSISTANT_ID]):
    raise RuntimeError("Variáveis de ambiente obrigatórias ausentes.")

TZ = ZoneInfo(TIMEZONE)

client = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI(title="TecBrilho Middleware - Erika Google Agenda")


# ----------------------------
# Modelos de entrada / saída
# ----------------------------

class BotConversaPayload(BaseModel):
    data: Optional[str] = None
    hora: Optional[str] = None
    nome: Optional[str] = None
    carro: Optional[str] = None
    duracao: Optional[str] = None
    servicos: Optional[str] = None
    telefone: Optional[str] = None
    categoria: Optional[str] = None
    historico: Optional[str] = None


class BotConversaResponse(BaseModel):
    # Estrutura que o BotConversa espera: send[0].value
    send: List[Dict[str, Any]]


# ----------------------------
# Google Calendar helpers
# ----------------------------

def get_calendar_service():
    """
    Cria o client autenticado do Google Calendar usando o JSON
    do service account armazenado na variável GOOGLE_SERVICE_ACCOUNT_INFO.
    """
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_INFO)
    credentials = service_account.Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/calendar"],
    )
    service = build("calendar", "v3", credentials=credentials)
    return service


def parse_date_time(date_str: str, time_str: str) -> datetime:
    """
    Converte data (dd/mm/yyyy ou yyyy-mm-dd) + hora (HH:MM ou HHhMM)
    em datetime com fuso da TIMEZONE.
    Assume que a Erika BotConversa já converteu expressões
    como “amanhã”, “sábado” para uma data explícita.
    """
    # Data
    date_str = (date_str or "").strip()
    if not date_str:
        raise ValueError("data vazia")

    try:
        # Formato ISO
        dt_date = datetime.fromisoformat(date_str).date()
    except ValueError:
        # Formato brasileiro
        dt_date = datetime.strptime(date_str, "%d/%m/%Y").date()

    # Hora
    time_str = (time_str or "").strip().lower()
    time_str = time_str.replace("h", ":")
    if len(time_str) == 4 and ":" not in time_str:
        # Ex: 0900 -> 09:00
        time_str = time_str[:2] + ":" + time_str[2:]
    dt_time = datetime.strptime(time_str, "%H:%M").time()

    dt = datetime.combine(dt_date, dt_time)
    return dt.replace(tzinfo=TZ)


def create_google_calendar_event(
    *,
    date: str,
    start_time: str,
    duration_minutes: int,
    client_name: str,
    phone: str,
    car_model: Optional[str],
    service_name: str,
    category: str,
    conversation_summary: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Implementa a função create_calendar_event chamada pelo Assistente.
    NÃO revalida capacidade (isso fica nas instruções do Assistente).
    Apenas grava o evento no Google Agenda.
    """
    start_dt = parse_date_time(date, start_time)
    end_dt = start_dt + timedelta(minutes=int(duration_minutes))

    summary = f"{service_name} - {client_name}"
    description_lines = [
        f"Cliente: {client_name}",
        f"Telefone: {phone}",
    ]
    if car_model:
        description_lines.append(f"Veículo: {car_model}")
    description_lines.append(f"Categoria: {category}")
    if conversation_summary:
        description_lines.append("")
        description_lines.append("Resumo da conversa:")
        description_lines.append(conversation_summary)

    event_body = {
        "summary": summary,
        "description": "\n".join(description_lines),
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": TIMEZONE,
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": TIMEZONE,
        },
        "extendedProperties": {
            "private": {
                "srv_calendar": category,
                "phone": phone,
            }
        },
    }

    service = get_calendar_service()
    created = service.events().insert(
        calendarId=GOOGLE_CALENDAR_ID,
        body=event_body,
    ).execute()

    return {
        "event_id": created.get("id"),
        "html_link": created.get("htmlLink"),
        "start": created.get("start"),
        "end": created.get("end"),
    }


# ----------------------------
# OpenAI Assistants helpers
# ----------------------------

def call_erika_google_agenda(payload: BotConversaPayload) -> str:
    """
    Envia os dados do BotConversa para a Erika Google Agenda
    e devolve a mensagem que deve ser enviada ao cliente.
    """
    # Monta mensagem única para o Assistente (contexto bem estruturado)
    user_content = f"""
    Você é a Erika Google Agenda, responsável por confirmar e registrar
    agendamentos no Google Agenda da TecBrilho.

    Dados recebidos do BotConversa:

    - nome_cliente: {payload.nome}
    - tel_cliente: {payload.telefone}
    - modelo_carro: {payload.carro}
    - servicos_ctrd: {payload.servicos}
    - srv_calendar: {payload.categoria}
    - data_agnd: {payload.data}
    - hora_agnd: {payload.hora}
    - durac_min: {payload.duracao}

    Histórico da conversa (WhatsApp):
    {payload.historico}

    Sua tarefa:
    1. Validar se há dados suficientes e se o horário respeita as regras
       operacionais e de capacidade da TecBrilho.
    2. Se estiver tudo certo, chame a função create_calendar_event
       com os argumentos corretos.
    3. Após a criação do evento, responda com uma única mensagem em português,
       pronta para ser enviada ao cliente pelo WhatsApp.
    4. Se houver algum problema, explique o motivo e sugira um novo horário.
    """

    # Cria thread
    thread = client.beta.threads.create()

    # Adiciona mensagem do usuário
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_content.strip(),
    )

    # Executa o Assistente
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id,
        assistant_id=OPENAI_ASSISTANT_ID,
    )

    # Se o Assistente pediu para chamar ferramentas
    if run.status == "requires_action":
        tool_calls = run.required_action.submit_tool_outputs.tool_calls
        tool_outputs = []

        for tool_call in tool_calls:
            func_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments or "{}")

            if func_name == "create_calendar_event":
                # Extrai argumentos, com defaults seguros
                event_result = create_google_calendar_event(
                    date=args.get("date") or (payload.data or ""),
                    start_time=args.get("start_time") or (payload.hora or "09:00"),
                    duration_minutes=int(
                        args.get("duration_minutes")
                        or (payload.duracao or "60")
                    ),
                    client_name=args.get("client_name") or (payload.nome or "Cliente"),
                    phone=args.get("phone") or (payload.telefone or ""),
                    car_model=args.get("car_model") or payload.carro,
                    service_name=args.get("service_name") or (payload.servicos or "Serviço TecBrilho"),
                    category=args.get("category") or (payload.categoria or "geral"),
                    conversation_summary=args.get("conversation_summary") or payload.historico,
                )

                tool_outputs.append(
                    {
                        "tool_call_id": tool_call.id,
                        "output": json.dumps(event_result),
                    }
                )
            else:
                # Se surgirem outras funções no futuro, apenas devolvemos
                tool_outputs.append(
                    {
                        "tool_call_id": tool_call.id,
                        "output": json.dumps({"error": "Função não implementada no middleware."}),
                    }
                )

        # Envia outputs e espera conclusão
        run = client.beta.threads.runs.submit_tool_outputs_and_poll(
            thread_id=thread.id,
            run_id=run.id,
            tool_outputs=tool_outputs,
        )

    if run.status != "completed":
        # Alguma falha / timeout / erro
        raise RuntimeError(f"Run do Assistente não completou. Status: {run.status}")

    # Pega a última mensagem do Assistente
    messages = client.beta.threads.messages.list(thread_id=thread.id)
    # messages.data[0] é a mais recente
    for msg in messages.data:
        if msg.role == "assistant":
            # Assume um único bloco de texto
            for part in msg.content:
                if part.type == "text":
                    return part.text.value

    # Fallback
    return "Seu agendamento foi processado, mas não consegui recuperar a mensagem de confirmação. Por favor, tente novamente ou fale com um atendente humano."


# ----------------------------
# Rota de Webhook BotConversa
# ----------------------------

@app.post("/webhook/agendar", response_model=BotConversaResponse)
async def webhook_agendar(request: Request):
    """
    Endpoint chamado pelo bloco de integração do BotConversa.
    Recebe os campos personalizados e responde com a mensagem
    que deve ser enviada ao cliente.
    """
    raw_body = await request.json()

    # Suporta tanto {data: ...} quanto {"root": {...}}
    if "root" in raw_body and isinstance(raw_body["root"], dict):
        data = raw_body["root"]
    else:
        data = raw_body

    try:
        payload = BotConversaPayload(**data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Payload inválido: {e}")

    try:
        msg_cliente = call_erika_google_agenda(payload)
    except Exception as e:
        # Em caso de erro, devolvemos uma mensagem amigável
        msg_cliente = (
            "Tive um problema ao tentar confirmar seu agendamento agora. "
            "Nossa equipe vai revisar manualmente e te chamar em seguida. "
            "Se preferir, pode mandar um 'oi' de novo mais tarde. 😉"
        )
        # LOG real: print / Sentry / etc.
        print("Erro ao processar agendamento:", repr(e))

    # Resposta no formato esperado pelo BotConversa
    return BotConversaResponse(
        send=[{"value": msg_cliente}]
    )
