
import os
from datetime import datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from assistant import send_to_erika
from calendar_manager import (
    create_event,
    is_time_available,
    get_calendar_id_by_category,
)

app = FastAPI()


@app.get("/")
def root():
    return {
        "status": "online",
        "service": "TecBrilho Middleware",
        "version": "1.0",
    }


# ============================================================
# 1) WEBHOOK DE CONVERSA (ERIKA → WHATSAPP)
# ============================================================
@app.post("/webhook_chat")
async def webhook_chat(request: Request):
    data = await request.json()

    # Campos típicos do BotConversa
    user_message = data.get("message") or data.get("text") or ""
    phone = data.get("phone") or data.get("from") or ""
    # Você pode optar por usar contactId como thread_id para manter contexto por contato
    thread_id = data.get("thread_id") or data.get("contactId") or None

    if not user_message:
        return JSONResponse(
            {
                "send": [
                    {
                        "type": "text",
                        "value": "Não recebi nenhuma mensagem para responder 😅",
                    }
                ]
            }
        )

    try:
        erika_response, updated_thread_id = send_to_erika(user_message, thread_id)
    except Exception as e:
        return JSONResponse(
            {
                "send": [
                    {
                        "type": "text",
                        "value": (
                            "Tive um probleminha técnico aqui agora, mas já podemos "
                            "tentar de novo em instantes, tudo bem? 🙏"
                        ),
                    }
                ],
                "variables": {
                    "erro_interno": str(e),
                },
            }
        )

    # Nota interna resumida
    nota = (
        f"Cliente ({phone}) → '{user_message[:120]}' | "
        f"Erika → '{erika_response[:160]}'"
    )

    return JSONResponse(
        {
            "send": [
                {
                    "type": "text",
                    "value": erika_response,
                }
            ],
            "variables": {
                "thread_id": updated_thread_id,
                "nota": nota,
            },
        }
    )


# ============================================================
# 2) WEBHOOK DE AGENDAMENTO (GOOGLE CALENDAR)
# ============================================================
@app.post("/webhook_schedule")
async def webhook_schedule(request: Request):
    data = await request.json()

    # Dados vindos do BotConversa (ajuste os nomes das variáveis no fluxo)
    nome = data.get("cliente_nome") or data.get("name")
    telefone = data.get("telefone") or data.get("phone")
    veiculo = data.get("veiculo_modelo")
    servico = data.get("servico")
    categoria = data.get("categoria")  # polimentos, higienizacao, etc.

    data_str = data.get("data") or data.get("date")  # formato YYYY-MM-DD
    hora_inicio = data.get("hora_inicio") or data.get("time_start")  # HH:MM

    duracao_minutos = int(data.get("duracao_minutos", data.get("duration", 60)))
    resumo_conversa = data.get("resumo_conversa") or data.get("note", "")

    # Validação básica
    if not all([nome, telefone, veiculo, servico, categoria, data_str, hora_inicio]):
        return JSONResponse(
            {
                "send": [
                    {
                        "type": "text",
                        "value": (
                            "Parece que faltaram algumas informações pra finalizar o "
                            "agendamento. Você pode revisar os dados e me enviar de novo, "
                            "por favor?"
                        ),
                    }
                ]
            }
        )

    # Montando datetime de início/fim
    try:
        inicio = datetime.fromisoformat(f"{data_str}T{hora_inicio}:00")
    except Exception:
        return JSONResponse(
            {
                "send": [
                    {
                        "type": "text",
                        "value": (
                            "O formato da data ou do horário não ficou claro pro sistema. "
                            "Você consegue reenviar esses dados, por favor? 🙏"
                        ),
                    }
                ]
            }
        )

    fim = inicio + timedelta(minutes=duracao_minutos)

    # Título e descrição do evento (Google Agenda)
    summary = f"{servico} – {nome}"

    description_lines = [
        f"Cliente: {nome}",
        f"Telefone: {telefone}",
        f"Veículo: {veiculo}",
        f"Serviço contratado: {servico}",
        "",
        "Resumo da conversa:",
        resumo_conversa or "Sem resumo informado.",
        "",
        "Origem: WhatsApp – BotConversa (Erika TecBrilho)",
    ]
    description = "\n".join(description_lines)

    # Verificação de disponibilidade
    try:
        calendar_id = get_calendar_id_by_category(categoria)
        livre = is_time_available(calendar_id, inicio, fim)
    except Exception:
        # Se der algum problema pra checar, segue em frente (melhor não travar)
        livre = True

    if not livre:
        return JSONResponse(
            {
                "send": [
                    {
                        "type": "text",
                        "value": (
                            f"{nome}, esse horário já está ocupado na nossa agenda. "
                            "Você consegue outro horário próximo? Posso te sugerir "
                            "algumas opções em seguida. 😊"
                        ),
                    }
                ]
            }
        )

    # Criação de evento
    try:
        event = create_event(
            category=categoria,
            start=inicio,
            end=fim,
            summary=summary,
            description=description,
        )
    except Exception as e:
        return JSONResponse(
            {
                "send": [
                    {
                        "type": "text",
                        "value": (
                            "Tentei registrar seu horário na nossa agenda, mas aconteceu "
                            "um erro técnico aqui. Você se importa de tentar novamente "
                            "em alguns instantes ou falar com alguém do time? 😕"
                        ),
                    }
                ],
                "variables": {
                    "erro_agenda": str(e),
                },
            }
        )

    # Mensagem de confirmação para o cliente
    dia_formatado = inicio.strftime("%d/%m/%Y")
    hora_formatada = inicio.strftime("%H:%M")

    texto_cliente = (
        f"Perfeito, {nome}! Já deixei agendado o serviço de *{servico}* "
        f"para *{dia_formatado} às {hora_formatada}* aqui na TecBrilho. 🚗✨\n\n"
        "Pode ficar tranquilo, vamos cuidar bem do seu carro!"
    )

    return JSONResponse(
        {
            "send": [
                {
                    "type": "text",
                    "value": texto_cliente,
                }
            ],
            "variables": {
                "event_id": event.get("id"),
                "calendar_category": categoria,
            },
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
