import logging
from typing import Dict, Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_service():
    """Create a Google Calendar API service client using a single calendar.

    We use the service account JSON stored in settings.google_service_account_info.
    """
    creds = service_account.Credentials.from_service_account_info(
        settings.google_service_account_info, scopes=SCOPES
    )
    service = build("calendar", "v3", credentials=creds)
    return service


def create_calendar_event(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create an event in the single TecBrilho Google Calendar.

    Expected keys in `data` (after processing by the OpenAI assistant Erika Agenda):
        - nome: str
        - telefone: str
        - carro: str
        - servicos: str
        - categoria: str (optional, used only for description/log)
        - inicio: str (ISO 8601 with timezone)
        - fim: str (ISO 8601 with timezone)
        - descricao: str
    """
    service = _get_service()
    calendar_id = settings.google_calendar_id

    start_iso = data.get("inicio")
    end_iso = data.get("fim")

    if not start_iso or not end_iso:
        raise ValueError("Campos 'inicio' e 'fim' são obrigatórios para criar o evento.")

    summary = data.get("servicos") or "Atendimento TecBrilho"
    nome = data.get("nome") or ""
    if nome:
        summary = f"{summary} – {nome}"

    description = data.get("descricao") or ""
    telefone = data.get("telefone") or ""
    carro = data.get("carro") or ""
    categoria = data.get("categoria") or ""

    extra_lines = []
    if telefone:
        extra_lines.append(f"Telefone: {telefone}")
    if carro:
        extra_lines.append(f"Veículo: {carro}")
    if categoria:
        extra_lines.append(f"Categoria: {categoria}")

    if extra_lines:
        description = description + "\n\n" + "\n".join(extra_lines)

    event_body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_iso},
        "end": {"dateTime": end_iso},
    }

    event = service.events().insert(calendarId=calendar_id, body=event_body).execute()

    logger.info("Evento criado no calendário %s: %s", calendar_id, event.get("id"))

    return {
        "calendar_id": calendar_id,
        "event_id": event.get("id"),
        "html_link": event.get("htmlLink"),
        "start": start_iso,
        "end": end_iso,
    }
