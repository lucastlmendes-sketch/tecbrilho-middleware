# state_store.py
"""
State Store
-----------
Armazena dados simples de forma persistente (opcional) usando um arquivo JSON.

Esse recurso serve como utilitário de debug ou para manter rastreamento
mínimo de threads utilizadas nos agendamentos.

Ele não é crítico para o funcionamento do middleware,
mas auxilia no monitoramento e auditoria caso necessário.
"""

import json
import os
import logging

logger = logging.getLogger(__name__)

STATE_FILE = "state_store.json"


class StateStore:
    def __init__(self):
        # Se o arquivo não existir, cria com estrutura básica
        if not os.path.exists(STATE_FILE):
            self._write({"threads": {}})
        logger.info("[StateStore] Inicializado.")

    # -----------------------------------------------------------
    # LEITURA DE DADOS
    # -----------------------------------------------------------
    def _read(self) -> dict:
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.exception("[StateStore] Erro ao ler state_store.json: %s", exc)
            return {"threads": {}}

    # -----------------------------------------------------------
    # ESCRITA DE DADOS
    # -----------------------------------------------------------
    def _write(self, data: dict):
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.exception("[StateStore] Erro ao salvar state_store.json: %s", exc)

    # -----------------------------------------------------------
    # REGISTRAR THREAD DO OPENAI
    # -----------------------------------------------------------
    def save_thread(self, contact_id: str, thread_id: str):
        data = self._read()
        data["threads"][contact_id] = thread_id
        self._write(data)

    # -----------------------------------------------------------
    # BUSCAR THREAD ANTERIOR
    # -----------------------------------------------------------
    def get_thread(self, contact_id: str) -> str | None:
        data = self._read()
        return data["threads"].get(contact_id)


# Instância exportada
state_store = StateStore()
