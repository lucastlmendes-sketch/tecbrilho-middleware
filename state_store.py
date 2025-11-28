# state_store.py
"""
State Store (Versão A - simples e opcional)
-------------------------------------------
Na Arquitetura A, o assistente OpenAI (Erika Agenda)
é 100% responsável por controlar lógica, memória de curto prazo
e criação de eventos.

O backend permanece totalmente "stateless".

Este módulo existe apenas para expansões futuras.
"""

import logging

logger = logging.getLogger("StateStore")


class StateStore:
    """
    Armazena estados mínimos em memória (runtime).
    Não persiste nada — seguro para uso em Render.
    """

    def __init__(self):
        self._store = {}
        logger.info("StateStore inicializado (modo leve).")

    # ---------------------------------------------------
    # MÉTODOS BÁSICOS
    # ---------------------------------------------------

    def set(self, key: str, value):
        """Grava um valor na memória volátil."""
        self._store[key] = value
        logger.debug(f"[STATE] SET {key} = {value}")

    def get(self, key: str, default=None):
        """Lê um valor do estado."""
        return self._store.get(key, default)

    def delete(self, key: str):
        """Remove um item específico."""
        if key in self._store:
            del self._store[key]
            logger.debug(f"[STATE] DEL {key}")

    def clear(self):
        """Limpa todo o estado."""
        self._store.clear()
        logger.debug("[STATE] CLEAR")


# Instância global — mantém compatibilidade com importações externas
state_store = StateStore()
