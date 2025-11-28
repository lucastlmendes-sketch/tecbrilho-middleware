import os
import json
import logging
import hashlib
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, ValidationError

from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from openai import OpenAI


# =========================
#  CONFIGURAÇÃO DE LOGS
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("tecbrilho-middleware")

print("[BOOT] TecBrilho Middleware iniciando...")


# =========================
#  VARIÁVEIS DE AMBIENTE
# =========================

GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
GOOGLE_SERVICE_ACCOUNT_INFO = os.getenv("GOOGLE_SERVICE_ACCOUNT_INFO")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ASSISTANT_ID = os.getenv("OPENAI_AGENDA_ASSISTANT_ID")
TIMEZONE = os.getenv("TIMEZONE", "America/Sao_Paulo")

REQUIRED_ENVS = {
    "GOOGLE_CALENDAR_ID": GOOGLE_CALENDAR_ID,
    "GOOGLE_SERVICE_ACCOUNT_INFO": GOOGLE_SERVICE_ACCOUNT_INFO,
    "OPENAI_API_KEY": OPENAI_API_KEY,
    "OPENAI_AGENDA_ASSISTANT_ID": OPENAI_ASSISTANT_ID,
}

missing_envs = [name for name, value in REQUIRED_ENVS.items() if not value]
if missing_envs:
    msg = f"Variáveis de ambiente ausentes: {', '.join(missing_envs)}"
    logger.error(msg)
    raise RuntimeError(msg)

TZ = ZoneInfo(TIMEZONE)

client = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI(title="TecBrilho Middleware - Erika Google Agenda")


# =========================
#  MODELOS DA API
# =========================

class BotConversaPayload(BaseModel):
    # nomes pensados para bater com o corpo do bloco de integração
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
    send: List[Dict[str, Any]]


# =========================
#  FUNÇÕES UTILITÁRIAS
# =========================

def sanitize_str(value: Optional[str]) -> str:
    """Remove None, 'undefined', 'null', espaços duplicados etc."""
    if not value:
        return ""
    v = str(value).strip()
    if v.lower() in {"undefined", "null", "none"}:
        return ""
    # remove caracteres de controle e normaliza espaços
    v = re.sub(r"\s+", " ", v)
    return v


def safe_int(value: Any, default: int = 60) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def normalize_date(date_str: str) -> str:
    """
    Aceita formatos comuns: DD/MM/YYYY, YYYY-MM-DD, DD-MM-YYYY
    Retorna sempre YYYY-MM-DD (ISO).
    """
    date_str = sanitize_str(date_str)
    if not date_str:
        raise ValueError("Data vazia")

    # Tenta ISO direto
    try:
        return datetime.fromisoformat(date_str).date().isoformat()
    except ValueError:
        pass

    # Tenta DD/MM/YYYY
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt).date().isoformat()
        except ValueError:
            continue

    raise ValueError(f"Formato de data inválido: {date_str}")


def normalize_time(time_str: str) -> str:
    """
    Aceita: '09:00', '9:00', '09h', '9h', '0900'
    Retorna HH:MM
    """
    time_str = sanitize_str(time_str).lower().replace("h", ":")
    if not time_str:
        raise ValueError("Hora vazia")

    # 0900 -> 09:00
    if time_str.isdigit() and len(time_str) == 4:
        time_str = time_str[:2] + ":" + time_str[2:]

    # Se só veio '9' ou '9:' -> assume :00
    if re.fullmatch(r"\d{1,2}", time_str):
        time_str = f"{int(time_str):02d}:00"

    if re.fullmatch(r"\d{1,2}:", time_str):
        time_str = f"{int(time_str[:-1]):02d}:00"

    dt_time = datetime.strptime(time_str, "%H:%M").time()
    return dt_time.strftime("%H:%M")


def parse_start_end_datetime(date_str: str, time_str: str, duration_minutes: int) -> Tuple[datetime, datetime]:
    iso_date = normalize_date(date_str)
    norm_time = normalize_time(time_str)

    date_obj = datetime.fromisoformat(iso_date).date()
    time_obj = datetime.strptime(norm_time, "%H:%M").time()

    start = datetime.combine(date_obj, time_obj).replace(tzinfo=TZ)
    end = start + timedelta(minutes=duration_minutes)
    return start, end


def compress_conversation_history(history: Optional[str], max_chars: int = 3000) -> str:
    """
    Compressão simples:
    - remove emojis (básico)
    - remove espaços duplicados
    - se ficar muito grande, mantém começo e fim.
    """
    if not history:
        return ""

    text = str(history)
    # Remove alguns ranges de emoji comuns (bem simples, não perfeito)
    text = re.sub(r"[\U0001F300-\U0001FAFF]", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) <= max_chars:
        return text

    head = text[: max_chars // 2]
    tail = text[-max_chars // 2 :]
    return head + " ... [resumo truncado] ... " + tail


def compute_event_hash(
    *,
    client_name: str,
    phone: str,
    service_name: str,
    start_iso: str,
    end_iso: str,
) -> str:
    """
    Gera um hash estável para evitar duplicação de eventos.
    """
    key = "|".join(
        [
            sanitize_str(client_name),
            sanitize_str(phone),
            sanitize_str(service_name),
            start_iso,
            end_iso,
        ]
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


# =========================
#  GOOGLE CALENDAR
# =========================

def get_calendar_service():
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_INFO)
    credentials = service_account.Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/calendar"],
    )
    service = build("calendar", "v3", credentials=credentials)
    return service


def find_existing_event_by_hash(
    service,
    calendar_id: str,
    event_hash: str,
    start: datetime,
    end: datetime,
) -> Optional[Dict[str, Any]]:
    """
    Procura evento com mesmo hash no intervalo do dia.
    """
    time_min = start.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    time_max = start.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()

    try:
        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
    except HttpError as e:
        logger.error(f"Erro ao listar eventos para deduplicação: {e}")
        return None

    for event in events_result.get("items", []):
        ext = event.get("extendedProperties", {}).get("private", {})
        if ext.get("event_hash") == event_hash:
            return event

    return None


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
    Cria um evento no Google Calendar com deduplicação e tratamento de erros.
    """
    logger.info(
        f"[CALENDAR] Iniciando criação de evento para {client_name} - {service_name}"
    )

    start_dt, end_dt = parse_start_end_datetime(date, start_time, duration_minutes)
    start_iso = start_dt.isoformat()
    end_iso = end_dt.isoformat()

    event_hash = compute_event_hash(
        client_name=client_name,
        phone=phone,
        service_name=service_name,
        start_iso=start_iso,
        end_iso=end_iso,
    )

    summary = f"{service_name} - {client_name}"
    description_lines = [
        f"Cliente: {client_name}",
        f"Telefone: {phone}",
    ]
    if car_model:
        description_lines.append(f"Veículo: {car_model}")
    description_lines.append(f"Categoria interna: {category}")
    if conversation_summary:
        description_lines.append("")
        description_lines.append("Resumo da conversa:")
        description_lines.append(conversation_summary)

    event_body = {
        "summary": summary,
        "description": "\n".join(description_lines),
        "start": {
            "dateTime": start_iso,
            "timeZone": TIMEZONE,
        },
        "end": {
            "dateTime": end_iso,
            "timeZone": TIMEZONE,
        },
        "extendedProperties": {
            "private": {
                "event_hash": event_hash,
                "srv_calendar": category,
                "phone": phone,
            }
        },
    }

    service = get_calendar_service()

    # Deduplicação
    existing = find_existing_event_by_hash(
        service, GOOGLE_CALENDAR_ID, event_hash, start_dt, end_dt
    )
    if existing:
        logger.warning(
            f"[CALENDAR] Evento duplicado detectado, reutilizando ID {existing.get('id')}"
        )
        return {
            "event_id": existing.get("id"),
            "html_link": existing.get("htmlLink"),
            "start": existing.get("start"),
            "end": existing.get("end"),
            "deduplicated": True,
        }

    # Tentativas com retry
    last_error = None
    for attempt in range(3):
        try:
            created = (
                service.events()
                .insert(calendarId=GOOGLE_CALENDAR_ID, body=event_body)
                .execute()
            )
            logger.info(
                f"[AUDIT] Evento criado com sucesso: ID={created.get('id')} "
                f"Cliente={client_name} Serviço={service_name}"
            )
            return {
                "event_id": created.get("id"),
                "html_link": created.get("htmlLink"),
                "start": created.get("start"),
                "end": created.get("end"),
                "deduplicated": False,
            }
        except HttpError as e:
            last_error = e
            logger.error(f"[CALENDAR] Erro ao criar evento (tentativa {attempt+1}/3): {e}")
    # Se chegou aqui, falhou mesmo depois de retries
    raise RuntimeError(f"Falha ao criar evento no Google Calendar: {last_error}")


# =========================
#  OPENAI / ASSISTANT
# =========================

def call_erika_google_agenda(payload: BotConversaPayload) -> str:
    """
    Envia os dados do BotConversa para o Assistente Erika Google Agenda,
    gerencia function calling e devolve uma mensagem única em português
    pronta para o cliente.
    """

    # Sanitiza / normaliza dados
    nome = sanitize_str(payload.nome)
    telefone = sanitize_str(payload.telefone)
    carro = sanitize_str(payload.carro)
    servicos = sanitize_str(payload.servicos)
    categoria = sanitize_str(payload.categoria)
    data_agnd = sanitize_str(payload.data)
    hora_agnd = sanitize_str(payload.hora)
    durac_min = safe_int(payload.duracao, default=60)
    historico = compress_conversation_history(payload.historico)

    # Mensagem de contexto para o assistente (técnico, não comercial)
    user_content = f"""
Você é a Erika Google Agenda. Você recebe dados estruturados do BotConversa
e sua única função é decidir se deve chamar a função create_calendar_event.

Use **apenas** os dados abaixo, não invente nada.

Dados recebidos:

- nome_cliente: {nome}
- tel_cliente: {telefone}
- modelo_carro: {carro}
- servicos_ctrd: {servicos}
- srv_calendar: {categoria}
- data_agnd: {data_agnd}
- hora_agnd: {hora_agnd}
- durac_min: {durac_min}

Resumo do histórico de conversa (se existir):
{historico}

Regras:

1. Se algum dos campos essenciais estiver vazio (nome_cliente, tel_cliente, servicos_ctrd,
   srv_calendar, data_agnd, hora_agnd, durac_min), NÃO chame função nenhuma.
   Em vez disso, responda com uma mensagem curta em português explicando
   qual dado está faltando para poder finalizar o agendamento.

2. Se todos os campos estiverem preenchidos, chame a função create_calendar_event
   usando exatamente esses valores, apenas convertendo data/hora se precisar.

3. Depois que a função create_calendar_event for executada e retornar sucesso,
   responda com UMA frase curta em português, confirmando o agendamento
   (data, horário e serviço) e dizendo que o cliente fez uma ótima escolha.

Sua resposta final deve ser APENAS o texto para o cliente, em português,
sem JSON, sem detalhes técnicos.
""".strip()

    logger.info("[OPENAI] Criando thread para Erika Google Agenda")

    # Cria thread
    thread = client.beta.threads.create()

    # Mensagem do "usuário" (sistema interno)
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_content,
    )

    # Executa o Assistente (com retries)
    run = None
    last_error = None
    for attempt in range(3):
        try:
            run = client.beta.threads.runs.create_and_poll(
                thread_id=thread.id,
                assistant_id=OPENAI_ASSISTANT_ID,
            )
            break
        except Exception as e:
            last_error = e
            logger.error(f"[OPENAI] Erro ao criar/poll run (tentativa {attempt+1}/3): {e}")

    if run is None:
        raise RuntimeError(f"Falha ao iniciar run na OpenAI: {last_error}")

    # Se o assistente pediu para chamar funções
    if run.status == "requires_action":
        logger.info("[OPENAI] Run requer ação de ferramenta (function calling)")
        tool_calls = run.required_action.submit_tool_outputs.tool_calls
        tool_outputs = []

        for tool_call in tool_calls:
            func_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments or "{}")
            logger.info(f"[OPENAI] Tool call recebida: {func_name} - args: {args}")

            if func_name == "create_calendar_event":
                try:
                    event_result = create_google_calendar_event(
                        date=args.get("date") or data_agnd,
                        start_time=args.get("start_time") or hora_agnd,
                        duration_minutes=int(
                            args.get("duration_minutes", durac_min) or durac_min
                        ),
                        client_name=args.get("client_name") or nome or "Cliente",
                        phone=args.get("phone") or telefone or "",
                        car_model=args.get("car_model") or carro,
                        service_name=args.get("service_name") or servicos or "Serviço TecBrilho",
                        category=args.get("category") or categoria or "geral",
                        conversation_summary=args.get("conversation_summary") or historico,
                    )
                    output = json.dumps(
                        {"ok": True, "event": event_result},
                        ensure_ascii=False,
                    )
                except Exception as e:
                    logger.error(f"[CALENDAR] Erro na função create_calendar_event: {e}")
                    output = json.dumps(
                        {"ok": False, "error": str(e)},
                        ensure_ascii=False,
                    )
            else:
                logger.warning(f"[OPENAI] Função não implementada: {func_name}")
                output = json.dumps(
                    {"ok": False, "error": "Função não implementada no middleware."},
                    ensure_ascii=False,
                )

            tool_outputs.append(
                {
                    "tool_call_id": tool_call.id,
                    "output": output,
                }
            )

        # Envia os outputs de ferramenta e espera o assistente concluir
        run = client.beta.threads.runs.submit_tool_outputs_and_poll(
            thread_id=thread.id,
            run_id=run.id,
            tool_outputs=tool_outputs,
        )

    if run.status != "completed":
        logger.error(f"[OPENAI] Run não completou. Status: {run.status}")
        raise RuntimeError(f"Run do assistente não completou. Status: {run.status}")

    # Recupera a mensagem final da Erika Google Agenda
    messages = client.beta.threads.messages.list(thread_id=thread.id)

    for msg in messages.data:
        if msg.role == "assistant":
            # Pega o primeiro bloco de texto
            for part in msg.content:
                if part.type == "text":
                    text = part.text.value.strip()
                    logger.info(f"[OPENAI] Mensagem final da Erika Google Agenda: {text}")
                    return text

    # Fallback se por algum motivo não encontrar texto
    logger.error("[OPENAI] Não foi possível recuperar mensagem de texto do assistente.")
    return (
        "Seu agendamento foi processado, mas tive uma dificuldade técnica para "
        "gerar a mensagem de confirmação. Nosso time vai conferir manualmente "
        "e te chamar em seguida. 😊"
    )


# =========================
#  ENDPOINT DO WEBHOOK
# =========================

@app.post("/webhook/agendar", response_model=BotConversaResponse)
async def webhook_agendar(request: Request):
    """
    Endpoint chamado pelo bloco de integração do BotConversa.

    Estrutura típica de corpo configurada no bloco de integração:

    {
      "data": "{data_agnd}",
      "hora": "{hora_agnd}",
      "nome": "{nome_cliente}",
      "carro": "{modelo_carro}",
      "duracao": "{durac_min}",
      "servicos": "{servicos_ctrd}",
      "telefone": "{tel_cliente}",
      "categoria": "{srv_calendar}",
      "historico": "{HistóricoConversas}"
    }
    """
    try:
        raw_body = await request.json()
    except Exception as e:
        logger.error(f"[WEBHOOK] Erro ao ler JSON: {e}")
        raise HTTPException(status_code=400, detail="JSON inválido")

    logger.info(f"[WEBHOOK] Payload recebido: {raw_body}")
    print(f"[WEBHOOK] Payload recebido (print): {raw_body}")

    # Alguns fluxos do BotConversa podem encapsular em "root"
    if isinstance(raw_body, dict) and "root" in raw_body and isinstance(raw_body["root"], dict):
        data = raw_body["root"]
    else:
        data = raw_body

    # Validação do payload
    try:
        payload = BotConversaPayload(**data)
    except ValidationError as e:
        logger.error(f"[WEBHOOK] Payload inválido: {e}")
        raise HTTPException(status_code=400, detail=f"Payload inválido: {e}")

    try:
        msg_cliente = call_erika_google_agenda(payload)
    except Exception as e:
        logger.error(f"[WEBHOOK] Erro ao processar agendamento: {e}")
        print(f"[WEBHOOK] Erro ao processar agendamento (print): {e}")

        msg_cliente = (
            "Tive um problema ao tentar confirmar seu agendamento agora. "
            "Nossa equipe vai revisar manualmente e te chamar em seguida, "
            "tudo bem? Se preferir, pode mandar um 'oi' de novo mais tarde. 😉"
        )

    return BotConversaResponse(send=[{"value": msg_cliente}])


# =========================
#  HEALTHCHECK SIMPLES
# =========================

@app.get("/health")
async def health():
    return {"status": "ok"}
