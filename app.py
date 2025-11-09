import os
import json
import datetime
import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from openai import OpenAI

# ---------------------------------------------------------
# Configurações básicas
# ---------------------------------------------------------
app = FastAPI()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")  # Erika
KOMMO_TOKEN = os.getenv("KOMMO_TOKEN")                  # token da API Kommo
KOMMO_DOMAIN = os.getenv("KOMMO_DOMAIN")                # ex: "https://tecbrilho.kommo.com"

client = OpenAI(api_key=OPENAI_API_KEY)


# ---------------------------------------------------------
# Função: chamar a Erika na OpenAI (Assistants)
# ---------------------------------------------------------
def call_openai_erika(user_message: str) -> str:
    """
    Envia a mensagem do cliente para a Erika (Assistente da OpenAI)
    e devolve apenas o texto da resposta.
    """

    if not OPENAI_ASSISTANT_ID:
        # fallback: se por algum motivo não tiver ID configurado
        # evita quebrar a aplicação
        return (
            "Oi! Aqui é a Erika da TecBrilho. "
            "No momento estou com uma indisponibilidade técnica, "
            "mas já já tudo volta ao normal. 😊"
        )

    try:
        # Cria uma resposta usando o Assistente configurado (Erika)
        # Aqui usamos a API de Responses com um assistant_id já treinado no painel.
        response = client.responses.create(
            model="gpt-4.1-mini",
            assistant_id=OPENAI_ASSISTANT_ID,
            input=[
                {
                    "role": "user",
                    "content": user_message,
                }
            ],
        )

        # Extrai o texto final
        for item in response.output:
            if item.type == "message":
                for content_part in item.message.content:
                    if content_part.type == "output_text":
                        return content_part.output_text.text

        # Fallback caso algo diferente aconteça
        return (
            "Oi! Sou a Erika da TecBrilho. "
            "Recebi sua mensagem, mas tive um pequeno problema para gerar a resposta completa. "
            "Pode me mandar de novo ou explicar um pouco mais, por favor? 😊"
        )

    except Exception as e:
        print(f"[ERRO OPENAI] {e}")
        return (
            "Tive um problema técnico ao processar sua mensagem agora. "
            "Você pode tentar novamente em alguns instantes, por favor? 🙏"
        )


# ---------------------------------------------------------
# Rotas básicas (teste / health)
# ---------------------------------------------------------
@app.get("/")
async def root():
    return PlainTextResponse("Kommo ⇆ OpenAI middleware is running.")


@app.get("/health")
async def health():
    return PlainTextResponse("ok")


# ---------------------------------------------------------
# Webhook do Kommo
# ---------------------------------------------------------
@app.post("/kommo-webhook")
async def kommo_webhook(request: Request):
    """
    Endpoint que recebe os eventos do Kommo.
    - Lê o payload (se houver JSON válido)
    - Extrai a mensagem de texto do cliente
    - Chama a Erika na OpenAI
    - Cria uma nota no lead (se houver lead_id)
    - Devolve JSON simples pro Kommo
    """

    # 1) Ler o corpo cru primeiro, para evitar JSONDecodeError
    body_bytes = await request.body()
    if not body_bytes:
        # Kommo às vezes pode mandar requisições sem corpo (pings/testes)
        print("[WEBHOOK] Corpo vazio recebido, ignorando.")
        return JSONResponse(
            {"status": "ignored", "reason": "empty body"},
            status_code=200,
        )

    try:
        payload = json.loads(body_bytes)
    except json.JSONDecodeError as e:
        print(f"[WEBHOOK] JSON inválido recebido: {e} | body={body_bytes!r}")
        return JSONResponse(
            {"status": "ignored", "reason": "invalid json"},
            status_code=200,
        )

    print(f"[WEBHOOK] Payload recebido às {datetime.datetime.now()}: {payload}")

    # 2) Extrair mensagem de texto (vários formatos possíveis do Kommo)
    message = (
        payload.get("message", {}).get("text")
        or payload.get("text")
        or payload.get("last_message", {}).get("text")
        or ""
    )

    # 3) Extrair informações de lead (se vier)
    lead = payload.get("lead") or {}
    lead_id = lead.get("id") or payload.get("lead_id")

    if not message:
        # Não há texto pra responder → não chama a IA
        print("[WEBHOOK] Payload sem campo de mensagem de texto, ignorando.")
        return JSONResponse(
            {
                "status": "ignored",
                "reason": "sem mensagem",
                "payload_keys": list(payload.keys()),
            },
            status_code=200,
        )

    # 4) Chamar a Erika na OpenAI
    ai_response = call_openai_erika(message)
    print(f"[ERIKA] Resposta gerada: {ai_response}")

    # 5) Criar nota no lead no Kommo (se tivermos lead_id + token + domínio)
    kommo_note_status = "skipped"
    error_msg = ""

    if lead_id and KOMMO_TOKEN and KOMMO_DOMAIN:
        try:
            note_data = {
                "note_type": "common",
                "params": {"text": f"🧠 Erika (IA TecBrilho): {ai_response}"},
            }

            r = requests.post(
                f"{KOMMO_DOMAIN}/api/v4/leads/{lead_id}/notes",
                headers={"Authorization": f"Bearer {KOMMO_TOKEN}"},
                json=note_data,
                timeout=30,
            )
            r.raise_for_status()
            kommo_note_status = "ok"
            print(f"[KOMMO] Nota criada com sucesso no lead {lead_id}.")
        except Exception as e:
            kommo_note_status = "failed"
            error_msg = str(e)
            print(f"[ERRO KOMMO] Falha ao criar nota no lead {lead_id}: {e}")

    else:
        print(
            "[KOMMO] Nota não enviada: faltando lead_id ou variáveis KOMMO_TOKEN/KOMMO_DOMAIN."
        )

    # 6) Devolver resposta JSON (Kommo não usa o texto, mas é útil pra debug)
    return JSONResponse(
        {
            "status": "ok",
            "lead_id": lead_id,
            "ai_response": ai_response,
            "kommo_note": kommo_note_status,
            "error": error_msg,
        },
        status_code=200,
    )
