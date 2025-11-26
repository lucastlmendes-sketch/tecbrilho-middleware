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
    key = service_type.lower().strip()
    cal_id = settings.calendar_ids.get(key)
    if not cal_id:
        raise ValueError(f"Calendário não configurado: {service_type}")
    return cal_id


def create_calendar_event_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recebe o formato convertido pelo openai_client:
    {
      service_type,
      title,
      start_iso,
      end_iso,
      description,
      ...
    }
    """

    service_type = args.get("service_type", "polimentos")
    title = args.get("title")
    description = args.get("description")
    start_iso = args.get("start_iso")
    end_iso = args.get("end_iso")

    if not all([title, start_iso, end_iso]):
        raise ValueError("start_iso, end_iso e title são obrigatórios.")

    cal_id = _pick_calendar_id(service_type)
    service = _get_service()

    event_body = {
        "summary": title,
        "description": description or "",
        "start": {"dateTime": start_iso, "timeZone": settings.timezone},
        "end": {"dateTime": end_iso, "timeZone": settings.timezone},
        "reminders": {"useDefault": True},
    }

    event = service.events().insert(calendarId=cal_id, body=event_body).execute()

    return {
        "calendar_id": cal_id,
        "event_id": event.get("id"),
        "html_link": event.get("htmlLink"),
    }
