# calendar_client.py
"""
Google Calendar Client
----------------------
Responsável por criar eventos no Google Calendar usando um
Service Account.

Mesmo que o Assistente OpenAI Agenda possa criar eventos diretamente,
mantemos esta classe para compatibilidade futura e para suportar
function calling, caso seja habilitado mais tarde.
"""

from __future__ import annotations

import datetime
import pytz
from google.oauth2 import service_account
from googleapiclient.discovery import build
from config import settings


class GoogleCalendarClient:
    """Cliente responsável por criar eventos no Google Calendar."""

    def __init__(self):
        creds = service_account.Credentials.from_service_account_info(
            settings.google_service_account_info,
            scopes=["https://www.googleapis.com/auth/calendar"]
        )
        self.service = build("calendar", "v3", credentials=creds)
        self.calendar_id = settings.google_calendar_id
        self.tz = pytz.timezone(settings.timezone)

    # ----------------------------------------------------------
    # Criação de evento no Google Calendar
    # ----------------------------------------------------------
    def create_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        description: str = "",
        location: str = "",
    ) -> dict:
        """
        Cria um evento no calendário Google.

        Params:
            title (str)       – Título do evento
            start_time (str)  – Horário inicial (ISO 8601)
            end_time (str)    – Horário final   (ISO 8601)
            description (str) – Descrição do evento
            location (str)    – Local (opcional)

        Returns:
            dict contendo o evento criado.
        """

        event_body = {
            "summary": title,
            "description": description,
            "location": location,
            "start": {
                "dateTime": start_time,
                "timeZone": settings.timezone,
            },
            "end": {
                "dateTime": end_time,
                "timeZone": settings.timezone,
            }
        }

        event = (
            self.service.events()
            .insert(calendarId=self.calendar_id, body=event_body)
            .execute()
        )

        return event


# Instância única exportada
calendar_client = GoogleCalendarClient()
