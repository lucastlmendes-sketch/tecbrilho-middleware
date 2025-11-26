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
    """
    Cliente de comunicação com o Assistente da OpenAI.
    Compatível com strict mode e funções padronizadas.
    """

    def __init__(self, state_store: StateStore):
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.assistant_id = settings.openai_assistant_id
        self.state_store = state_store

    # ============================================================
    # ENTRADA PRINCIPAL (chamada pelo webhook)
    # ============================================================
    async def handle_message(
        self,
        contact_id: str,
        phone: str,
        message: str,
        contact_name: Optional[str] = None,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:

        # 1. Carregar thread do contato
        thread_id = self.state_store.get_thread_id(contact_id)
        if not thread_id:
            thread = self.client.beta.threads.create(
                metadata={"contact_id": contact_id, "phone": phone}
            )
            thread_id = thread.id
            self.state_store.set_thread_id(contact_id, thread_id)

        # 2. Injetar contexto + mensagem real
        user_msg = self._build_message(phone, message, contact_name, extra_context)

        # 3. Registrar mensagem do usuário
        self.client.beta.threads.messages.create(
            thread_id=thread_id, role="user", content=user_msg
        )

        # 4. Criar run e aguardar
        run = self.client.beta.threads.runs.create_and_poll(
            thread_id=thread_id, assistant_id=self.assistant_id
        )

        # 5. Se o assistente chamar ferramentas
        while run.status == "requires_action":
            tool_outputs = []
            tool_calls = run.required_action.submit_tool_outputs.tool_calls

            for call in tool_calls:
                fn = call.function.name
                args_raw = call.function.arguments or "{}"

                try:
                    args = json.loads(args_raw)
                except:
                    args = {}
                    logger.error("Falha ao parsear argumentos de função: %s", args_raw)

                logger.info("TOOL CALL: %s => %s", fn, args)

                # ==========================
                # ROTAS DE FERRAMENTA
                # ==========================

                if fn == "create_calendar_event":
                    result = self._tool_create_event(args)

                elif fn == "tag_contact":
                    args.setdefault("contact_id", contact_id)
                    result = botconversa_client.tag_contact_tool(args)

                elif fn == "get_contact_context":
                    args.setdefault("contact_id", contact_id)
                    args.setdefault("phone", phone)
                    result = botconversa_client.get_contact_context_tool(args)

                else:
                    result = {"error": f"Função desconhecida: {fn}"}

                tool_outputs.append(
                    {
                        "tool_call_id": call.id,
                        "output": json.dumps(result, ensure_ascii=False),
                    }
                )

            run = self.client.beta.threads.runs.submit_tool_outputs_and_poll(
                thread_id=thread_id, run_id=run.id, tool_outputs=tool_outputs
            )

        # 6. Extrair resposta final do assistente
        return self._extract_assistant_message(thread_id)

    # ============================================================
    # Funções internas auxiliares
    # ============================================================

    def _build_message(
        self,
        phone: str,
        original_message: str,
        contact_name: Optional[str],
        extra_context: Optional[Dict[str, Any]],
    ) -> str:
        """
        Gera o bloco de contexto + mensagem do cliente.
        Compatível com strict mode do Assistants.
        """

        ctx = []
        ctx.append("INFORMAÇÃO GERADA PELO SISTEMA (não foi o cliente que escreveu):")

        ctx.append(f"- Telefone: {phone}")
      if contact_name and contact_name.lower() not in ["[nome]", "nome", ""]:
    ctx.append(f"- Nome (BotConversa): {contact_name}")

        if extra_context:
            bc = extra_context.get("botconversa_contact", {})
            if bc.get("tags"):
                ctx.append(f"- Tags no BotConversa: {', '.join(bc['tags'])}")
            if bc.get("custom_fields"):
                try:
                    cf = json.dumps(bc["custom_fields"], ensure_ascii=False)
                except:
                    cf = str(bc["custom_fields"])
                ctx.append(f"- Campos extras: {cf}")

        ctx_block = "\n".join(ctx)

        return f"{ctx_block}\n\n---\n\nMensagem do cliente:\n{original_message}"

    # ============================================================
    # Ferramenta Interna: create_calendar_event
    # (strict mode → campos padronizados)
    # ============================================================
    def _tool_create_event(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Converte strict mode da função para o formato aceito pelo calendário.
        """

        # Campos obrigatórios do strict mode
        title = args.get("title")
        start_time = args.get("start_time")
        end_time = args.get("end_time")
        description = args.get("description")
        location = args.get("location")  # não usado, mas aceitamos
        attendees = args.get("attendees", [])
        reminders = args.get("reminders", [])

        if not all([title, start_time, end_time, description]):
            return {
                "error": "Campos obrigatórios ausentes para create_calendar_event (strict mode)."
            }

        # Converter strict mode → formato interno
        internal_args = {
            "service_type": self._infer_service_type(title),
            "title": title,
            "description": description,
            "start_iso": start_time,
            "end_iso": end_time,
            "customer_name": None,
            "customer_phone": None,
        }

        try:
            return calendar_client.create_calendar_event_tool(internal_args)
        except Exception as exc:
            logger.exception("Erro ao criar evento no calendário: %s", exc)
            return {"error": str(exc)}

    def _infer_service_type(self, title: str) -> str:
        """
        Tenta inferir o tipo de serviço a partir do título.
        Caso a Erika não especifique, assumimos polimentos.
        """
        title_l = title.lower()

        if "higien" in title_l:
            return "higienizacao"
        if "lav" in title_l:
            return "lavagens"
        if "pelíc" in title_l or "pelic" in title_l:
            return "peliculas"
        if "instal" in title_l or "multim" in title_l:
            return "instalacoes"
        if "farol" in title_l:
            return "martelinho"
        if "rolê" in title_l or "role" in title_l:
            return "role_guarulhos"

        return "polimentos"

    # ============================================================
    # Saída da Erika
    # ============================================================
    def _extract_assistant_message(self, thread_id: str) -> Tuple[str, str]:
        msgs = self.client.beta.threads.messages.list(
            thread_id=thread_id, order="desc", limit=10
        )

        for msg in msgs.data:
            if msg.role == "assistant":
                parts = []
                for c in msg.content:
                    if c.type == "text":
                        parts.append(c.text.value)

                if parts:
                    return ("\n".join(parts), thread_id)

        raise RuntimeError("Nenhuma resposta do assistente encontrada.")
