import json
import logging
import time
from typing import Dict, Any, List

from openai import OpenAI

from config import settings
import calendar_client

logger = logging.getLogger(__name__)


class OpenAIChatClient:
    """Wrapper around the OpenAI client to talk to assistants.

    For this stage we only use the Erika Agenda assistant to create calendar events.
    """

    def __init__(self) -> None:
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.agenda_assistant_id = settings.openai_agenda_assistant_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run_agenda_assistant(self, payload: Dict[str, Any]) -> str:
        """Use the Erika Agenda assistant to create a calendar event.

        `payload` is the JSON recebido do BotConversa:
            {
              "nome": "...",
              "telefone": "...",
              "carro": "...",
              "servicos": "...",
              "categoria": "...",
              "data": "...",
              "hora": "...",
              "duracao": "...",
              ...
            }
        """
        # Normaliza os campos vindos do BotConversa
        nome = (payload.get("nome") or "").strip()
        telefone = (payload.get("telefone") or "").strip()
        carro = (payload.get("carro") or "").strip()
        servicos = (payload.get("servicos") or "").strip()
        categoria = (payload.get("categoria") or "").strip()
        data = (payload.get("data") or "").strip()
        hora = (payload.get("hora") or "").strip()
        duracao_raw = str(payload.get("duracao") or "").strip()
        historico = (payload.get("historico") or "").strip()

        try:
            duracao_min = int(duracao_raw) if duracao_raw else None
        except ValueError:
            duracao_min = None

        user_payload = {
            "nome": nome,
            "telefone": telefone,
            "carro": carro,
            "servicos": servicos,
            "categoria": categoria,
            "data": data,
            "hora": hora,
            "duracao_minutos": duracao_min,
            "historico": historico,
            "timezone": settings.timezone,
        }

        logger.info(
            "[AGENDA] Chamando Erika Agenda com payload: %s",
            json.dumps(user_payload, ensure_ascii=False),
        )

        thread = self.client.beta.threads.create(
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Você é a Erika Agenda, responsável por transformar as intenções "
                        "de agendamento em eventos reais no Google Agenda TecBrilho. "
                        "Receba o JSON a seguir, valide dados, calcule horários de início/fim "
                        f"no timezone {settings.timezone}, respeitando duração, e chame a ferramenta "
                        "`create_calendar_event` exatamente uma vez para criar o evento. "
                        "Depois responda com uma frase curta e clara em português confirmando "
                        "o agendamento para o cliente. "
                        "JSON do cliente:\n"
                        f"{json.dumps(user_payload, ensure_ascii=False)}"
                    ),
                }
            ]
        )

        run = self.client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=self.agenda_assistant_id,
        )

        # Processa o run até terminar (tratando tool_calls)
        final_run = self._process_run_with_tools(thread.id, run.id)

        if final_run.status != "completed":
            logger.error("[AGENDA] Run finalizou com status %s", final_run.status)
            return (
                "Tive um problema para confirmar seu agendamento agora. "
                "Pode tentar novamente em alguns instantes?"
            )

        # Recupera a última mensagem do assistente
        return self._get_last_assistant_message(thread.id)

    # ------------------------------------------------------------------
    # Tool processing internals
    # ------------------------------------------------------------------
    def _process_run_with_tools(self, thread_id: str, run_id: str):
        """Poll the run until completion, handling tool calls when required."""
        while True:
            run = self.client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)

            if run.status == "requires_action":
                tool_outputs: List[Dict[str, str]] = []
                ra = run.required_action
                if ra and ra.type == "submit_tool_outputs":
                    for tool_call in ra.submit_tool_outputs.tool_calls:
                        fn_name = tool_call.function.name
                        raw_args = tool_call.function.arguments or "{}"
                        try:
                            args = json.loads(raw_args)
                        except json.JSONDecodeError:
                            args = {}

                        logger.info("[AGENDA] Tool call: %s args=%s", fn_name, raw_args)

                        if fn_name == "create_calendar_event":
                            try:
                                result = calendar_client.create_calendar_event(args)
                                output_str = json.dumps(result, ensure_ascii=False)
                            except Exception as exc:
                                logger.exception("Erro ao criar evento no calendário: %s", exc)
                                output_str = json.dumps(
                                    {
                                        "error": "Erro ao criar evento no Google Agenda.",
                                        "details": str(exc),
                                    },
                                    ensure_ascii=False,
                                )
                        else:
                            output_str = json.dumps(
                                {"error": f"Função de ferramenta desconhecida: {fn_name}"},
                                ensure_ascii=False,
                            )

                        tool_outputs.append(
                            {
                                "tool_call_id": tool_call.id,
                                "output": output_str,
                            }
                        )

                self.client.beta.threads.runs.submit_tool_outputs(
                    thread_id=thread_id,
                    run_id=run.id,
                    tool_outputs=tool_outputs,
                )
                time.sleep(0.5)
                continue

            if run.status in {"completed", "failed", "cancelled", "expired"}:
                return run

            time.sleep(0.7)

    def _get_last_assistant_message(self, thread_id: str) -> str:
        """Return the last assistant message text for the given thread."""
        messages = self.client.beta.threads.messages.list(
            thread_id=thread_id, order="desc", limit=10
        )

        for msg in messages.data:
            if msg.role == "assistant":
                parts: List[str] = []
                for c in msg.content:
                    if getattr(c, "type", None) == "text":
                        parts.append(c.text.value)
                if parts:
                    return "\n".join(parts)

        logger.warning("Nenhuma mensagem de assistente encontrada no thread %s", thread_id)
        return (
            "Seu agendamento foi processado, mas não consegui gerar a mensagem de confirmação "
            "automática. Se tiver alguma dúvida, fale com a equipe TecBrilho."
        )
