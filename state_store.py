import json
import os
import threading
from typing import Dict, Optional, Any


class StateStore:
    """Armazena informações por contato (thread_id, perfil, etc.).

    Continua compatível com o formato antigo:
      { "contact_id": "thread_xxx" }

    Novo formato (quando for atualizado):
      {
        "contact_id": {
          "thread_id": "thread_xxx",
          "profile": {
            "name": "João",
            "car_model": "Civic 2020",
            "last_service_interest": "Polimento",
            "funnel_stage": "Contato em Andamento"
          }
        }
      }
    """

    def __init__(self, path: str = "state_store.json"):
        self.path = path
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            self._data = {}
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except Exception:
            # Se der erro, começa vazio
            self._data = {}

    def _save(self) -> None:
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.path)

    # ---------------------------
    # API de thread do Assistente
    # ---------------------------

    def get_thread_id(self, contact_id: str) -> Optional[str]:
        with self._lock:
            value = self._data.get(contact_id)
            if isinstance(value, str):
                # Formato antigo
                return value
            if isinstance(value, dict):
                return value.get("thread_id")
            return None

    def set_thread_id(self, contact_id: str, thread_id: str) -> None:
        with self._lock:
            value = self._data.get(contact_id)
            if isinstance(value, dict):
                value["thread_id"] = thread_id
            else:
                # converte formato antigo -> novo
                self._data[contact_id] = {"thread_id": thread_id}
            self._save()

    # ---------------------------
    # API de "memória" de perfil
    # ---------------------------

    def get_profile(self, contact_id: str) -> Dict[str, Any]:
        """Retorna o perfil salvo para o contato (pode estar vazio)."""
        with self._lock:
            value = self._data.get(contact_id)
            if isinstance(value, dict):
                return dict(value.get("profile") or {})
            return {}

    def update_profile(self, contact_id: str, **fields: Any) -> Dict[str, Any]:
        """Atualiza campos do perfil (name, car_model, etc.)."""
        with self._lock:
            value = self._data.get(contact_id)
            if isinstance(value, dict):
                profile = value.get("profile") or {}
                profile.update({k: v for k, v in fields.items() if v is not None})
                value["profile"] = profile
                self._data[contact_id] = value
            else:
                # Se ainda estava no formato antigo (string), converte
                self._data[contact_id] = {
                    "thread_id": value if isinstance(value, str) else None,
                    "profile": {k: v for k, v in fields.items() if v is not None},
                }
            self._save()
            return dict(self._data[contact_id]["profile"])
