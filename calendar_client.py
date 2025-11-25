import datetime as dt
import logging
from typing import Dict, Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_service():
    creds = service_account.Credentials.from_service_account_info(
        settings.google_service_account_info,
        scopes=SCOPES,
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _pick_calendar_id(service_type: str) -> str:
    """Escolhe o calendário com base no tipo de serviço.

    O Assistente deve chamar a ferramenta passando um service_type
    compatível com as chaves abaixo (polimentos, higienizacao, etc.).
    """
    key = service_type.lower().strip()
    cal_id = settings.calendar_ids.get(key)
    if not cal_id:
        raise ValueError(f"Não existe calendário configurado para o serviço: {service_type}")
    return cal_id


def create_calendar_event_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Função usada pelo Assistente (via tool call).

    Espera um JSON com (por exemplo):

    {
      "service_type": "polimentos",
      "title": "Polimento TecBrilho - João",
      "description": "Detalhes do serviço",
      "start_iso": "2025-01-10T09:00:00",
      "end_iso": "2025-01-10T10:00:00",
      "customer_name": "João",
      "customer_phone": "+5511999999999"
    }
    """
    service_type = args.get("service_type") or "polimentos"
    title = args.get("title") or "Atendimento TecBrilho"
    description = args.get("description") or ""

    start_iso = args.get("start_iso")
    end_iso = args.get("end_iso")

    if not start_iso or not end_iso:
        raise ValueError("start_iso e end_iso são obrigatórios para criar o evento")

    calendar_id = _pick_calendar_id(service_type)
    service = _get_service()

    event_body = {
        "summary": title,
        "description": description,
        "start": {
            "dateTime": start_iso,
            "timeZone": settings.timezone,
        },
        "end": {
            "dateTime": end_iso,
            "timeZone": settings.timezone,
        },
        "reminders": {
            "useDefault": True,
        },
    }

    event = service.events().insert(calendarId=calendar_id, body=event_body).execute()
    logger.info("Evento criado no calendário %s: %s", calendar_id, event.get("id"))

    return {
        "calendar_id": calendar_id,
        "event_id": event.get("id"),
        "html_link": event.get("htmlLink"),
    }
