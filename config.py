import os
import json
from dataclasses import dataclass


@dataclass
class Settings:
    """Application settings loaded from environment variables."""

    openai_api_key: str
    timezone: str
    google_service_account_info: dict
    google_calendar_id: str

    @classmethod
    def load(cls) -> "Settings":

        # -----------------------
        # OPENAI API KEY
        # -----------------------
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise RuntimeError("OPENAI_API_KEY não definido no ambiente.")

        # -----------------------
        # TIMEZONE
        # -----------------------
        timezone = os.getenv("TIMEZONE", "America/Sao_Paulo")

        # -----------------------
        # GOOGLE SERVICE ACCOUNT (JSON)
        # -----------------------
        info_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_INFO")
        if not info_str:
            raise RuntimeError(
                "GOOGLE_SERVICE_ACCOUNT_INFO não definido no Render. Cole o JSON do Service Account completo."
            )

        try:
            google_service_account_info = json.loads(info_str)
        except Exception as exc:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_INFO não é um JSON válido.") from exc

        # -----------------------
        # GOOGLE CALENDAR ID
        # -----------------------
        google_calendar_id = os.getenv("GOOGLE_CALENDAR_ID")
        if not google_calendar_id:
            raise RuntimeError(
                "GOOGLE_CALENDAR_ID não definido. Ele deve ser o ID do calendário único que você escolheu."
            )

        return cls(
            openai_api_key=openai_api_key,
            timezone=timezone,
            google_service_account_info=google_service_account_info,
            google_calendar_id=google_calendar_id,
        )


settings = Settings.load()
