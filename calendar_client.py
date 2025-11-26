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


def
