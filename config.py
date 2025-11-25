import os
from dataclasses import dataclass
from typing import Dict, Optional
import json


@dataclass
class Settings:
    openai_api_key: str
    openai_assistant_id: str
    timezone: str
    google_service_account_info: dict
    calendar_ids: Dict[str, Optional[str]]

    @classmethod
    def load(cls) -> "Settings":
        openai_api_key = os.getenv("OPENAI_API_KEY", "")
        openai_assistant_id = os.getenv("OPENAI_ASSISTANT_ID", "")

        if not openai_api_key:
            raise RuntimeError("OPENAI_API_KEY não configurado")
        if not openai_assistant_id:
            raise RuntimeError("OPENAI_ASSISTANT_ID não configurado")

        timezone = os.getenv("TIMEZONE", "America/Sao_Paulo")

        raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if not raw_json:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON não configurado")
        try:
            info = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON não é um JSON válido") from exc

        # A chave privada costuma vir com \n. Convertendo para novas linhas reais:
        if "private_key" in info and isinstance(info["private_key"], str):
            info["private_key"] = info["private_key"].replace("\\n", "\n")

        calendar_ids = {
            "polimentos": os.getenv("CAL_POLIMENTOS_ID"),
            "higienizacao": os.getenv("CAL_HIGIENIZACAO_ID"),
            "lavagens": os.getenv("CAL_LAVAGENS_ID"),
            "peliculas": os.getenv("CAL_PELICULAS_ID"),
            "instalacoes": os.getenv("CAL_INSTALACOES_ID"),
            "martelinho": os.getenv("CAL_MARTELINHO_ID"),
            "role_guarulhos": os.getenv("CAL_ROLE_GUARULHOS_ID"),
        }

        return cls(
            openai_api_key=openai_api_key,
            openai_assistant_id=openai_assistant_id,
            timezone=timezone,
            google_service_account_info=info,
            calendar_ids=calendar_ids,
        )


settings = Settings.load()
