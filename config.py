# config.py
import os
import json
from dataclasses import dataclass
from typing import Optional


@dataclass
class Settings:
    """Application settings loaded from environment variables."""

    openai_api_key: str
    openai_agenda_assistant_id: str
    timezone: str
    google_service_account_info: dict
    google_calendar_id: str

    @classmethod
    def load(cls) -> "Settings":
        # ----------------------------
        # OPENAI
        # ----------------------------
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise RuntimeError("OPENAI_API_KEY não definido no ambiente.")

        openai_agenda_assistant_id = os.getenv("OPENAI_AGENDA_ASSISTANT_ID")
        if not openai_agenda_assistant_id:
            raise RuntimeError("OPENAI_AGENDA_ASSISTANT_ID não definido. Defina o assistente Erika Agenda.")

        # ----------------------------
        # TIMEZONE
        # ----------------------------
        timezone = os.getenv("TIMEZONE", "America/Sao_Paulo")

        # ----------------------------
        # GOOGLE SERVICE ACCOUNT JSON
        # ----------------------------
        info_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_INFO") or os.getenv(
            "GOOGLE_SERVICE_ACCOUNT_JSON"
        )
        if not info_str:
            raise RuntimeError(
                "GOOGLE_SERVICE_ACCOUNT_INFO/JSON não definido com as credenciais do Service Account."
            )

        try:
            google_service_account_info = json.loads(info_str)
        except json.JSONDecodeError as exc:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_INFO não é um JSON válido.") from exc

        # ----------------------------
        # CALENDÁRIO ÚNICO
        # ----------------------------
        google_calendar_id = (
            os.getenv("GOOGLE_CALENDAR_ID")
            or "0b6bf35d6ac040aaf0322365150b41f5603a8c9f92bd8b4a80ca16c6e905d2ca@group.calendar.google.com"
        )

        return cls(
            openai_api_key=openai_api_key,
            openai_agenda_assistant_id=openai_agenda_assistant_id,
            timezone=timezone,
            google_service_account_info=google_service_account_info,
            google_calendar_id=google_calendar_id,
        )


settings = Settings.load()
