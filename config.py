import os
import json
from dataclasses import dataclass
from typing import Optional


@dataclass
class Settings:
    """Application settings loaded from environment variables."""

    openai_api_key: str
    openai_chat_assistant_id: Optional[str]
    openai_agenda_assistant_id: str
    timezone: str
    google_service_account_info: dict
    google_calendar_id: str

    @classmethod
    def load(cls) -> "Settings":
        # OpenAI
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise RuntimeError("OPENAI_API_KEY não definido no ambiente.")

        # Assistente principal de chat (opcional neste momento)
        openai_chat_assistant_id = os.getenv("OPENAI_CHAT_ASSISTANT_ID") or os.getenv(
            "OPENAI_ASSISTANT_ID"
        )

        # Assistente responsável pelos agendamentos (Erika Agenda)
        openai_agenda_assistant_id = os.getenv("OPENAI_AGENDA_ASSISTANT_ID")
        if not openai_agenda_assistant_id:
            raise RuntimeError(
                "OPENAI_AGENDA_ASSISTANT_ID não definido. Defina o ID do assistente Erika Agenda."
            )

        # Timezone padrão
        timezone = os.getenv("TIMEZONE", "America/Sao_Paulo")

        # Credenciais do Google Service Account
        info_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_INFO") or os.getenv(
            "GOOGLE_SERVICE_ACCOUNT_JSON"
        )
        if not info_str:
            raise RuntimeError(
                "GOOGLE_SERVICE_ACCOUNT_INFO/JSON não definido com as credenciais do service account."
            )

        try:
            google_service_account_info = json.loads(info_str)
        except json.JSONDecodeError as exc:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_INFO não é um JSON válido.") from exc

        # ID único do calendário
        calendar_id = (
            os.getenv("GOOGLE_CALENDAR_ID")
            or os.getenv("CAL_DEFAULT_ID")
            or os.getenv("CAL_POLIMENTOS_ID")
        )
        if not calendar_id:
            raise RuntimeError(
                "Defina GOOGLE_CALENDAR_ID (ou CAL_DEFAULT_ID) com o ID do calendário do Google."
            )

        return cls(
            openai_api_key=openai_api_key,
            openai_chat_assistant_id=openai_chat_assistant_id,
            openai_agenda_assistant_id=openai_agenda_assistant_id,
            timezone=timezone,
            google_service_account_info=google_service_account_info,
            google_calendar_id=calendar_id,
        )


settings = Settings.load()
