import json
import os
import threading
from typing import Dict, Optional


class StateStore:
    """Armazena o thread_id do Assistente por contato.

    Usa um arquivo JSON simples. É suficiente para agora.
    """

    def __init__(self, path: str = "state_store.json"):
        self.path = path
        self._lock = threading.Lock()
        self._data: Dict[str, str] = {}
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

    def get_thread_id(self, contact_id: str) -> Optional[str]:
        with self._lock:
            return self._data.get(contact_id)

    def set_thread_id(self, contact_id: str, thread_id: str) -> None:
        with self._lock:
            self._data[contact_id] = thread_id
            self._save()
