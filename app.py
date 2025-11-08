import os
import datetime
import requests
from fastapi import FastAPI, HTTPException, Request

from openai import OpenAI

# Inicializa FastAPI
app = FastAPI()

# Cliente OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Configurações do Kommo
KOMMO_DOMAIN = os.getenv("KOMMO_DOMAIN", "").rstrip("/")
KOMMO_TOKEN = os.getenv("KOMMO_TOKEN", "")

# ID do assistente da Erika (criado na plataforma OpenAI)
ERIKA_ASSISTANT_ID = os.getenv("ERIKA_ASSISTANT_ID") or os.getenv("ZIDANE_ASSISTANT_ID")

if not ERIKA_ASSISTANT_ID:
    print("[ERRO] ERIKA_ASSISTANT_ID não configurado no ambiente.")

# -------------------------------------------------------------------
# Healthcheck
# -------------------------------------------------------------------
@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "kommo-middleware",
        "time": datetime.datetime.utcnow().isoformat(),
    }

# -------------------------------------------------------------------
# Função para chamar a Erika via OpenAI Assistants (Responses API)
# -------------------------------------------------------------------
def call_openai_erika(message: str) -> str:
    """
    Envia a mensagem do cliente para o assistente Erika na OpenAI
    e retorna apenas o texto da resposta.
    """
    if not ERIKA_ASSISTANT_ID:
        raise RuntimeError("ERIKA_ASSISTANT_ID não configurado.")

    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            assistant_id=ERIKA_ASSISTANT_ID,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": message,
                        }
                    ],
                }
            ],
        )

        # Extrai o texto da primeira saída
        output_text = ""
        for item in response.output:
            if item.type == "message":
                for content_part in item.message.content:
                    if content_part.type == "output_text":
                        output_text += content_part.text.value

        if not output_text:
            output_text = (
                "Desculpa, tive um problema momentâneo para gerar a resposta. "
                "Pode repetir a sua pergunta?"
            )

        return output_text.strip()

    except Exception as e:
        print(f"[ERRO] Falha ao chamar OpenAI: {e}")
        return (
            "Tive um probleminha técnico aqui, mas já pode tentar novamente "
            "ou falar com a equipe humana da TecBrilho. 🙏"
        )


# -------------------------------------------------------------------
# Webhook do Kommo
# -------------------------------------------------------------------
@app.post("/kommo-webhook")
async def kommo_webhook(request: Request):
    """
    Endpoint chamado pelo Kommo ao receber/atualizar mensagens.
    - Lê o payload
    - Extrai mensagem de texto e lead_id
    - Chama a Erika (OpenAI Assistants)
    - Cria uma nota no Kommo com a resposta
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload inválido ou ausente")

    print(f"[{datetime.datetime.utcnow().isoformat()}] Webhook recebido: {payload}")

    # Validação opcional de subdomínio (caso queira travar por segurança)
    account = payload.get("account", {}) or {}
    subdomain = account.get("subdomain") or account.get("name")
    authorized = os.getenv("AUTHORIZED_SUBDOMAIN")
    if authorized and subdomain and subdomain != authorized:
        raise HTTPException(
            status_code=401,
            detail=f"Subdomínio não autorizado: {subdomain}",
        )

    # Extrai mensagem
    message = (
        payload.get("message", {}).get("text")
        or payload.get("text")
        or payload.get("last_message", {}).get("text")
        or ""
    )

    # Extrai lead
    lead = payload.get("lead") or {}
    lead_id = lead.get("id") or payload.get("lead_id")

    if not message:
        # Nada para responder
        return {
            "status": "ignored",
            "reason": "sem mensagem",
            "payload_keys": list(payload.keys()),
        }

    # Chama Erika na OpenAI
    ai_response = call_openai_erika(message)

    # Se houver lead_id, tenta criar uma nota no Kommo
    note_result = "skipped"
    if lead_id and KOMMO_DOMAIN and KOMMO_TOKEN:
        try:
            # Kommo espera um ARRAY de notas
            note_data = [
                {
                    "entity_id": lead_id,
                    "note_type": "common",
                    "params": {
                        "text": f"Erika: {ai_response}",
                    },
                }
            ]

            url = f"{KOMMO_DOMAIN}/api/v4/leads/notes"
            headers = {
                "Authorization": f"Bearer {KOMMO_TOKEN}",
                "Content-Type": "application/json",
            }

            r = requests.post(url, json=note_data, headers=headers, timeout=30)
            print(f"[INFO] Kommo note response: {r.status_code} {r.text}")
            r.raise_for_status()
            note_result = "ok"

        except Exception as e:
            print(f"[ERRO] Falha ao criar nota no Kommo: {e}")
            note_result = "failed"

    return {
        "status": "ok",
        "lead_id": lead_id,
        "ai_response": ai_response,
        "kommo_note": note_result,
    }
