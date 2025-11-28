# openai_client.py
"""
OpenAI Client
-------------
Responsável pela comunicação com o Assistente Erika Agenda.

Fluxo:
    1. Criar thread
    2. Enviar mensagem com dados do agendamento
    3. Rodar assistente
    4. Esperar finalizar
    5. Capturar resposta final

Este client é usado pelo webhook /agenda-webhook no main.py.
"""

import time
from openai import OpenAI
from config import settings


class OpenAIChatClient:
    """Cliente responsável por conversar com o Assistente Erika Agenda."""

    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.assistant_id = settings.openai_agenda_assistant_id

    # ---------------------------------------------------------
    # Processa um agendamento usando o Assistente Agenda
    # ---------------------------------------------------------
    def process_agendamento(self, prompt: str) -> str:
        """
        Envia o prompt completo ao Assistente Agenda
        e retorna a mensagem final produzida pelo assistente.
        """

        # 1. Criar nova thread
        thread = self.client.beta.threads.create()

        # 2. Enviar a mensagem do usuário
        self.client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=prompt,
        )

        # 3. Rodar o assistente
        run = self.client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=self.assistant_id,
        )

        # 4. Esperar conclusão
        while True:
            status = self.client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id,
            )
            if status.status == "completed":
                break
            time.sleep(1)

        # 5. Buscar última resposta
        messages = self.client.beta.threads.messages.list(thread_id=thread.id)
        resposta = messages.data[0].content[0].text.value

        return resposta


# Instância exportada
openai_client = OpenAIChatClient()
