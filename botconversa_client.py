# botconversa_client.py
"""
BotConversa Client
------------------
Cliente simples para interagir com a API do BotConversa.

Ele permite:
 - enviar mensagens para um contato
 - adicionar tags
 - atualizar campos personalizados

Este arquivo é opcional, mas útil caso futuramente o middleware
precise interagir diretamente com o BotConversa.
"""

import os
import httpx
import logging


logger = logging.getLogger(__name__)


class BotConversaClient:
    def __init__(self):
        self.api_key = os.getenv("BOTCONVERSA_API_KEY")
        self.base_url = "https://backend.botconversa.com.br/api/v1"

        if not self.api_key:
            logger.warning("[BotConversa] BOTCONVERSA_API_KEY não encontrada.")

    # -------------------------------------------------------------
    # ENVIA MENSAGEM PARA UM CONTATO
    # -------------------------------------------------------------
    async def send_message(self, contact_id: str, text: str) -> bool:
        if not self.api_key:
            return False

        url = f"{self.base_url}/messages/send/"
        headers = {"Authorization": f"Token {self.api_key}"}

        payload = {
            "phone": contact_id,
            "message": text,
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    return True
                logger.error(
                    "[BotConversa] Erro ao enviar mensagem: %s",
                    resp.text
                )
        except Exception as exc:
            logger.exception("[BotConversa] Falha ao enviar mensagem: %s", exc)

        return False

    # -------------------------------------------------------------
    # APLICAR TAG EM UM CONTATO
    # -------------------------------------------------------------
    async def add_tag(self, contact_id: str, tag: str) -> bool:
        if not self.api_key:
            return False

        url = f"{self.base_url}/contacts/{contact_id}/tags/"
        headers = {"Authorization": f"Token {self.api_key}"}
        payload = {"tag": tag}

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, headers=headers, json=payload)
                return resp.status_code == 200
        except Exception as exc:
            logger.exception("[BotConversa] Falha ao adicionar tag: %s", exc)

        return False

    # -------------------------------------------------------------
    # ATUALIZAR CAMPOS PERSONALIZADOS
    # -------------------------------------------------------------
    async def update_custom_fields(self, contact_id: str, fields: dict) -> bool:
        if not self.api_key:
            return False

        url = f"{self.base_url}/contacts/{contact_id}/update/"
        headers = {"Authorization": f"Token {self.api_key}"}
        payload = {"custom_fields": fields}

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.patch(url, headers=headers, json=payload)
                return resp.status_code == 200
        except Exception as exc:
            logger.exception("[BotConversa] Erro ao atualizar campos personalizados: %s", exc)

        return False


# Instância padrão exportada
botconversa_client = BotConversaClient()
