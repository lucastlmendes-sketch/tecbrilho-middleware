# google_calendar.py
import json
import os
from typing import Optional, Dict, Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

TIMEZONE = os.getenv("TIMEZONE", "America/Sao_Paulo")

# Lê o JSON da service account do env
SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
if not SERVICE_ACCOUNT_JSON:
    raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON não configurado no ambiente.")

service_account_info = json.loads(SERVICE_ACCOUNT_JSON)

SCOPES = ["https://www.googleapis.com/auth/calendar"]

credentials = service_account.Credentials.from_service_account_info(
    service_account_info,
    scopes=SCOPES,
)

calendar_service = build("calendar", "v3", credentials=credentials)

# Map de serviços -> ID de calendário (vindo do .env / Render)
CALENDARS = {
    "POLIMENTOS": os.getenv("CAL_POLIMENTOS_ID"),
    "HIGIENIZACAO": os.getenv("CAL_HIGIENIZACAO_ID"),
    "LAVAGENS": os.getenv("CAL_LAVAGENS_ID"),
    "PELICULAS": os.getenv("CAL_PELICULAS_ID"),
    "INSTALACOES": os.getenv("CAL_INSTALACOES_ID"),
    "MARTELINHO": os.getenv("CAL_MARTELINHO_ID"),
    "ROLE_GUARULHOS": os.getenv("CAL_ROLE_GUARULHOS_ID"),
}


class CalendarError(Exception):
    """Erro genérico da agenda."""


def _resolve_calendar_id(payload: Dict[str, Any]) -> str:
    """
    Regras:
    - Se vier "calendar_id" no JSON da Erika, uso direto.
    - Senão, se vier "service_type" (POLIMENTOS, LAVAGENS, etc.), uso o map CALENDARS.
    """
    if "calendar_id" in payload and payload["calendar_id"]:
        return payload["calendar_id"]

    service_type = (payload.get("service_type") or "").upper()
    if service_type and service_type in CALENDARS and CALENDARS[service_type]:
        return CALENDARS[service_type]

    raise CalendarError(
        f"Não foi possível determinar o calendário. "
        f"service_type='{service_type}', calendar_id ausente."
    )


def create_event_from_payload(payload: Dict[str, Any], phone: str) -> Dict[str, Any]:
    """
    Espera um JSON mais ou menos assim (a Erika gera isso no final da resposta):

    ###CALENDAR: {
      "service_type": "HIGIENIZACAO",
      "start": "2025-11-26T14:00:00",
      "end": "2025-11-26T15:00:00",
      "summary": "Higienização para Lucas",
      "description": "Fox branco, reclamação de cheiro interno",
      "client_name": "Lucas",
      "client_phone": "+5511...."
    }

    Só "start" e "end" são obrigatórios aqui no código.
    """
    calendar_id = _resolve_calendar_id(payload)

    start = payload.get("start")
    end = payload.get("end")
    if not start or not end:
        raise CalendarError("Campos 'start' e 'end' são obrigatórios no payload.")

    summary = payload.get("summary") or "Atendimento TecBrilho"
    client_name = payload.get("client_name") or ""
    client_phone = payload.get("client_phone") or phone

    extra_desc = []
    if client_name:
        extra_desc.append(f"Cliente: {client_name}")
    if client_phone:
        extra_desc.append(f"Telefone: {client_phone}")

    base_description = payload.get("description") or ""
    if base_description:
        extra_desc.insert(0, base_description)

    description = "\n".join(extra_desc) if extra_desc else None

    event_body: Dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": start, "timeZone": TIMEZONE},
        "end": {"dateTime": end, "timeZone": TIMEZONE},
    }

    if description:
        event_body["description"] = description

    event = (
        calendar_service.events()
        .insert(calendarId=calendar_id, body=event_body)
        .execute()
    )

    return event
