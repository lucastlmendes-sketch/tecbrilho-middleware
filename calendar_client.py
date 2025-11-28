# calendar_client.py
"""
Google Calendar Client (Versão A)
---------------------------------
Nesta versão, o Assistente Erika Agenda é o único responsável
por criar eventos diretamente usando o Google Calendar Tool.

Este arquivo é mantido APENAS como base para expansões futuras
e para manter compatibilidade com versões B ou C caso você queira migrar.

Atualmente, NÃO criamos eventos daqui.
"""

import logging
from config import settings

logger = logging.getLogger("CalendarClient")


class GoogleCalendarClient:
    """
    Placeholder para compatibilidade futura.

    Nesta versão (A), o calendário é manipulado 100% pelo Assistente Agenda,
    portanto esta classe não executa ações diretas.
    """

    def __init__(self):
        self.calendar_id = settings.google_calendar_id

    def info(self):
        """
        Retorna informações básicas do calendário.
        """
        return {
            "calendar_id": self.calendar_id,
            "mode": "assistant_managed",  # modo atual (Erika Agenda faz tudo)
        }

    # ------------------------------------------------------------------
    # MÉTODOS FUTUROS (não utilizados hoje)
    # ------------------------------------------------------------------

    def create_event(self, *args, **kwargs):
        """
        Método reservado caso futuramente você queira criar eventos
        diretamente pelo backend em vez do Assistente.

        Atualmente não faz nada.
        """
        raise NotImplementedError(
            "Na versão A, o Assistente Agenda cria os eventos diretamente."
        )


# Instância global
calendar_client = GoogleCalendarClient()
