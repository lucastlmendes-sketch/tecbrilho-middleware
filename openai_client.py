import json
import logging
from typing import Tuple

from openai import OpenAI

from config import settings
from state_store import StateStore
import calendar_client
import botconversa_client

logger = logging.getLogger(__name__)


class OpenAIChatClient:
    def __init__(self, state_store: StateStore):
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.assistant_id = settings.openai_assistant_id
        self.state_store = state_store

    async def handle_message(self, contact_id: str, phone: str, message: str) -> Tuple[str, str]:
        """Envia a mensagem do cliente para o Assistente e devolve a resposta.

        Usa contact_id como identificador único do cliente, para manter o
        histórico da conversa.
        """
        thread_id = self.state_store.get_thread_id(contact_id)
        if not thread_id:
            thread = self.client.beta.threads.create(
                metadata={
                    "contact_id": contact_id,
                    "phone": phone,
                }
            )
            thread_id = thread.id
            self.state_store.set_thread_id(contact_id, thread_id)

        # Cria a mensagem do usuário (texto bruto vindo do BotConversa)
        self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=message,
        )

        # Cria um run e já faz o poll até terminar ou pedir ação
        run = self.client.beta.threads.runs.create_and_poll(
            thread_id=thread_id,
            assistant_id=self.assistant_id,
        )

        # Se o Assistente precisar chamar ferramentas (agenda, tags, etc.)
        while run.status == "requires_action":
            tool_outputs = []

            required = run.required_action
            if not required or required.type != "submit_tool_outputs":
                break

            for tool_call in required.submit_tool_outputs.tool_calls:
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments or "{}")

                logger.info("Tool call recebido: %s(%s)", function_name, arguments)

                if function_name == "create_calendar_event":
                    # Compatibiliza strict mode (start_time/end_time) com o calendário interno
                    args_conv = dict(arguments)
                    if "start_time" in args_conv and "start_iso" not in args_conv:
                        args_conv["start_iso"] = args_conv.pop("start_time")
                    if "end_time" in args_conv and "end_iso" not in args_conv:
                        args_conv["end_iso"] = args_conv.pop("end_time")

                    try:
                        result = calendar_client.create_calendar_event_tool(args_conv)
                    except Exception as exc:
                        logger.exception("Erro ao criar evento no calendário: %s", exc)
                        result = {"error": str(exc)}

                elif function_name == "tag_contact":
                    # Garante que o contact_id sempre esteja presente
                    arguments.setdefault("contact_id", contact_id)
                    result = botconversa_client.tag_contact_tool(arguments)

                elif function_name == "get_contact_context":
                    # Busca nome, tags e campos extras do contato no BotConversa
                    result = botconversa_client.get_contact_context_tool(arguments)

                else:
                    result = {
                        "error": f"Função de ferramenta desconhecida: {function_name}"
                    }

                tool_outputs.append(
                    {
                        "tool_call_id": tool_call.id,
                        "output": json.dumps(result, ensure_ascii=False),
                    }
                )

            run = self.client.beta.threads.runs.submit_tool_outputs_and_poll(
                thread_id=thread_id,
                run_id=run.id,
                tool_outputs=tool_outputs,
            )

        # Agora esperamos que o run esteja finalizado
        if run.status != "completed":
            logger.warning("Run não completou com sucesso. Status: %s", run.status)

        # Busca a última mensagem do assistente neste thread
        messages = self.client.beta.threads.messages.list(
            thread_id=thread_id,
            order="desc",
            limit=10,
        )

        for msg in messages.data:
            if msg.role == "assistant":
                # Pega apenas o texto concatenado
                parts = []
                for c in msg.content:
                    if c.type == "text":
                        parts.append(c.text.value)
                if parts:
                    answer = "\n".join(parts)
                    return answer, thread_id

        # Se por algum motivo não encontrarmos mensagem do assistente
        raise RuntimeError("Nenhuma resposta do assistente encontrada no thread")
