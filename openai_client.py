import json
import logging
from typing import Tuple, Optional, Dict, Any

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

    async def handle_message(
        self,
        contact_id: str,
        phone: str,
        message: str,
        contact_name: Optional[str] = None,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        """Envia a mensagem do cliente para o Assistente e devolve a resposta.

        - Usa contact_id como identificador único do cliente, para manter o
          histórico da conversa (thread).
        - Injeta contexto do BotConversa (nome, tags, campos extras) junto
          com a mensagem do cliente, para Erika se adaptar melhor.
        """
        # 1) Carrega/cria thread do contato
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

        # 2) Monta texto com contexto + mensagem do cliente
        user_text = self._build_user_message_with_context(
            phone=phone,
            original_message=message,
            contact_name=contact_name,
            extra_context=extra_context,
        )

        # 3) Cria mensagem do usuário no thread
        self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_text,
        )

        # 4) Cria um run e já faz o poll até terminar ou pedir ação
        run = self.client.beta.threads.runs.create_and_poll(
            thread_id=thread_id,
            assistant_id=self.assistant_id,
        )

        # 5) Se o Assistente precisar chamar ferramentas (agenda, tags, BotConversa, etc.)
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
                    result = calendar_client.create_calendar_event_tool(arguments)

                elif function_name == "tag_contact":
                    # Garante que o contact_id sempre esteja presente
                    arguments.setdefault("contact_id", contact_id)
                    result = botconversa_client.tag_contact_tool(arguments)

                elif function_name == "get_contact_context":
                    # Deixa o Assistente pedir dados do contato quando quiser
                    arguments.setdefault("contact_id", contact_id)
                    arguments.setdefault("phone", phone)
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

        # 6) Agora esperamos que o run esteja finalizado
        if run.status != "completed":
            logger.warning("Run não completou com sucesso. Status: %s", run.status)

        # 7) Busca a última mensagem do assistente neste thread
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

    # ------------------------------------------------------------------ #
    # Helpers                                                           #
    # ------------------------------------------------------------------ #

    def _build_user_message_with_context(
        self,
        phone: str,
        original_message: str,
        contact_name: Optional[str] = None,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Monta um texto que inclui contexto do sistema + mensagem do cliente.

        A ideia é dar para a Erika informações como:
          - nome (se conhecido)
          - telefone
          - tags
          - custom_fields do BotConversa (ex: modelo do carro)

        De forma clara, para ela não confundir com a fala do cliente.
        """
        context_lines = []

        if contact_name:
            context_lines.append(f"- Nome (origem: BotConversa): {contact_name}")
        context_lines.append(f"- Telefone: {phone}")

        if extra_context:
            bc_contact = extra_context.get("botconversa_contact") or {}
            tags = bc_contact.get("tags") or []
            custom_fields = bc_contact.get("custom_fields") or {}

            if tags:
                context_lines.append(f"- Tags no BotConversa: {', '.join(tags)}")

            if custom_fields:
                try:
                    cf_json = json.dumps(custom_fields, ensure_ascii=False)
                except Exception:
                    cf_json = str(custom_fields)
                context_lines.append(f"- Campos extras do BotConversa (custom_fields): {cf_json}")

        if not context_lines:
            # Sem contexto extra, envia só a mensagem mesmo
            return original_message

        context_block = (
            "INFORMAÇÃO GERADA PELO SISTEMA (não foi o cliente que escreveu):\n"
            + "\n".join(context_lines)
        )

        return f"{context_block}\n\n---\n\nMensagem do cliente:\n{original_message}"
