# openai_client.py
"""
OpenAI Client — Versão A (Assistente Erika Agenda faz tudo)
------------------------------------------------------------
Este módulo encapsula toda a comunicação com o Assistente da OpenAI.
Ele cria threads, envia prompts e retorna a resposta final.
"""

import time
import logging
from openai import OpenAI
from config import settings

logger = logging.getLogger("OpenAIClient")


# -------------------------------------------------------------
# Cliente oficial da OpenAI (v2)
# -------------------------------------------------------------
client = OpenAI(api_key=settings.openai_api_key)


class OpenAIClient:
    """
    Classe responsável por interagir com o Assistente Agenda (Erika Agenda)
    para criar eventos e gerar a resposta final.
    """

    def __init__(self):
        self.assistant_id = settings.openai_agenda_assistant_id

    # ---------------------------------------------------------
    # Função principal usada pelo middleware
    # ---------------------------------------------------------
    def process_agendamento(self, prompt: str) -> str:
        """
        Envia instruções ao Assistente Erika Agenda e retorna a mensagem final.
        """

        logger.info("📡 Enviando prompt ao Assistente Agenda...")

        # Criar thread
        thread = client.beta.threads.create()

        # Enviar mensagem de usuário
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=prompt,
        )

        # Criar execução (RUN)
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=self.assistant_id,
        )

        # Aguardar conclusão do assistente
        while True:
            status = client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id,
            )

            if status.status == "completed":
                break

            if status.status == "failed":
                raise RuntimeError("Assistente Agenda falhou ao processar o agendamento.")

            time.sleep(1)

        # Coletar resposta final
        messages = client.beta.threads.messages.list(thread_id=thread.id)

        for msg in messages.data:
            if msg.role == "assistant":
                texto = msg.content[0].text.value.strip()
                logger.info("📝 Resposta recebida do assistente: %s", texto)
                return texto

        # Caso nada seja encontrado
        raise RuntimeError("Nenhuma resposta válida do Assistente Agenda.")


# Instância global para uso no middleware
openai_client = OpenAIClient()
