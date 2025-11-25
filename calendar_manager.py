
import os
import json
import datetime as dt

from google.oauth2 import service_account
from googleapiclient.discovery import build

TIMEZONE = os.getenv("TIMEZONE", "America/Sao_Paulo")

CATEGORY_MAP = {
    "polimentos": "CAL_POLIMENTOS_ID",
    "higienizacao": "CAL_HIGIENIZACAO_ID",
    "lavagens": "CAL_LAVAGENS_ID",
    "peliculas": "CAL_PELICULAS_ID",
    "instalacoes": "CAL_INSTALACOES_ID",
    "martelinho": "CAL_MARTELINHO_ID",
    "role_guarulhos": "CAL_ROLE_GUARULHOS_ID",
}


def get_calendar_service():
    raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw_json:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON não configurado.")

    try:
        info = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON inválido.") from e

    credentials = service_account.Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/calendar"],
    )

    return build("calendar", "v3", credentials=credentials)


def get_calendar_id_by_category(category: str) -> str:
    key = CATEGORY_MAP.get(category)
    if not key:
        raise ValueError(f"Categoria de calendário inválida: {category}")

    cal_id = os.getenv(key)
    if not cal_id:
        raise RuntimeError(f"Variável de ambiente {key} não configurada.")

    return cal_id


def is_time_available(calendar_id: str, start: dt.datetime, end: dt.datetime) -> bool:
    service = get_calendar_service()

    events = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    return len(events.get("items", [])) == 0


def create_event(
    category: str,
    start: dt.datetime,
    end: dt.datetime,
    summary: str,
    description: str,
):
    calendar_id = get_calendar_id_by_category(category)
    service = get_calendar_service()

    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start.isoformat(), "timeZone": TIMEZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": TIMEZONE},
    }

    return service.events().insert(calendarId=calendar_id, body=body).execute()
