# botconversa_client.py
"""
BotConversa Client (Versão A)
-----------------------------
Como a arquitetura atual usa APENAS o webhook para comunicação,
este módulo é mantido apenas para compatibilidade e uso futuro.

Neste cenário:
- O BotConversa envia dados para o middleware.
- O middleware retorna a estrutura { "send": [...] }.
- Não existe comunicação ativa do middleware -> BotConversa.

Ainda assim, deixamos esta classe estruturada para expansões.
"""

import logging

logger = logging.getLogger("BotConversaClient")


class BotConversaClient:
    """
    Classe utilitária opcional para uma futura expansão,
    caso você deseje enviar mensagens ativamente ao BotConversa
    usando a API oficial deles.

    Na Arquitetura A, esta classe NÃO é usada.
    """

    def __init__(self):
        logger.info("BotConversaClient inicializado (modo passivo).")

    def send_message(self, contact_id: str, text: str):
        """
        Método de placeholder — não implementado.
        """
        logger.warning(
            "send_message() foi chamado, mas não há API configurada. "
            "O BotConversa é acionado apenas via webhook."
        )
        return {
            "status": "inactive",
            "detail": "Envio direto ao BotConversa não configurado nesta arquitetura."
        }

    def info(self):
        """
        Retorna apenas informações de estado.
        """
        return {
            "mode": "webhook_only",
            "description": (
                "O BotConversa envia eventos via webhook. "
                "O middleware não envia mensagens ativamente."
            ),
        }


# Instância global — mantém compatibilidade com importações
botconversa_client = BotConversaClient()
