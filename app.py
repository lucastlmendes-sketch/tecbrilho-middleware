from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests, os, datetime

app = FastAPI(title="Kommo ↔ TecBrilho Middleware (Erika / Zidane)")

# === Env vars ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
KOMMO_TOKEN = os.getenv("KOMMO_TOKEN")
KOMMO_DOMAIN = os.getenv("KOMMO_DOMAIN")  # ex.: https://tecnobrilho.kommo.com
ZIDANE_ASSISTANT_ID = os.getenv("ZIDANE_ASSISTANT_ID")  # opcional (usa fallback se não houver)

# Deriva subdomínio autorizado a partir do DOMÍNIO KOMMO
AUTHORIZED_SUBDOMAIN = None
if KOMMO_DOMAIN:
    host = KOMMO_DOMAIN.replace("https://", "").replace("http://", "")
    if host.endswith(".kommo.com"):
        AUTHORIZED_SUBDOMAIN = host.replace(".kommo.com", "")

# === CORS restrito ao domínio do Kommo (fallback para * se vazio) ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=[KOMMO_DOMAIN] if KOMMO_DOMAIN else ["*"],
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["Authorization", "Content-Type"],
)

# === Health & Home ===
@app.get("/")
def home():
    return {
        "status": "ok",
        "message": "Middleware ativo (Erika/Zidane)",
        "kommo_domain": KOMMO_DOMAIN,
    }


@app.get("/health")
def health():
    ok = bool(OPENAI_API_KEY and KOMMO_DOMAIN)
    return {"ok": ok, "timestamp": datetime.datetime.now().isoformat()}


@app.get("/ping")
def ping():
    return {"status": "alive", "ts": datetime.datetime.now().isoformat()}


# === Prompt fallback do Zidane/Erika (usado se não houver Assistant ID) ===
ZIDANE_PROMPT = (
    "Você é Erika, agente oficial da TecBrilho (baseada no Zidane), "
    "especialista em estética automotiva, vendas consultivas e organização de agenda. "
    "Crie conexão, entenda a dor do cliente e conduza para o serviço correto, "
    "sempre com frases curtas, empatia e foco em valor percebido. "
    "Colete nome, modelo/ano do veículo e alinhe se o serviço sugerido resolve o problema "
    "antes de falar de valores. Só depois apresente investimento e condições de pagamento, "
    "seguindo estritamente o catálogo TecBrilho."
)


def call_openai_zidane(user_message: str) -> str:
    """Chama o assistente da OpenAI (Erika/Zidane)."""

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    # 1) Tenta via Responses API com assistant_id (fluxo novo)
    if ZIDANE_ASSISTANT_ID:
        try:
            r = requests.post(
                "https://api.openai.com/v1/responses",
                headers=headers,
                json={
                    "assistant_id": ZIDANE_ASSISTANT_ID,
                    "input": [{"role": "user", "content": user_message}],
                },
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()

            # Estrutura típica da Responses API
            if "output" in data and isinstance(data["output"], list):
                for item in data["output"]:
                    if item.get("type") == "message":
                        parts = item["message"].get("content", [])
                        for part in parts:
                            if part.get("type") == "output_text":
                                return part.get("text", "").strip()

            # Fallback se a estrutura variar
            if "output_text" in data:
                return str(data["output_text"]).strip()

        except Exception:
            # Em caso de erro, cai para Chat Completions
            pass

    # 2) Fallback estável: Chat Completions com prompt da Erika/Zidane
    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": ZIDANE_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"Erro ao gerar resposta da IA: {e}"


# === Webhook Kommo ===
@app.post("/kommo-webhook")
async def kommo_webhook(request: Request):
    """
    Endpoint chamado pelo Kommo.
    O Kommo normalmente envia o payload no formato:
    {
      "event": "...",
      "account_id": ...,
      "data": {
          "message": {...},
          "lead": {...},
          ...
      }
    }
    Então aqui sempre tentamos ler primeiro de payload["data"].
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload inválido ou ausente")

    # Para debug: ver estrutura básica recebida
    print(
        f"[{datetime.datetime.now()}] Webhook recebido. "
        f"Top-level keys: {list(payload.keys())}"
    )

    # O Kommo costuma embrulhar tudo em "data"
    data = payload.get("data") or payload

    # Validação opcional do subdomínio do Kommo
    account_info = payload.get("account") or data.get("account") or {}
    subdomain = account_info.get("subdomain")

    if AUTHORIZED_SUBDOMAIN and subdomain and subdomain != AUTHORIZED_SUBDOMAIN:
        # Só bloqueia se veio um subdomínio diferente; se não veio nada, deixa passar.
        raise HTTPException(
            status_code=401,
            detail=f"Subdomínio não autorizado: {subdomain}",
        )

    # Extrai mensagem
    message = (
        (data.get("message") or {}).get("text")
        or (data.get("last_message") or {}).get("text")
        or data.get("text")
        or ""
    )

    # Extrai lead / lead_id
    lead = data.get("lead") or {}
    lead_id = (
        lead.get("id")
        or data.get("lead_id")
        or data.get("entity_id")
        or payload.get("lead_id")
    )

    if not message:
        # Quando isso aparecer nos logs, sabemos que o Kommo mandou
        # um evento sem texto (ex.: mudança de status, etc.)
        return {
            "status": "ignored",
            "reason": "sem mensagem",
            "payload_keys": list(payload.keys()),
            "data_keys": list(data.keys()),
        }

    print(
        f"[{datetime.datetime.now()}] Mensagem recebida do Kommo | "
        f"lead_id={lead_id} | texto='{message}'"
    )

    # Chama a IA (Erika/Zidane)
    resposta = call_openai_zidane(message)
    print(
        f"[{datetime.datetime.now()}] Resposta da IA para lead_id={lead_id}: {resposta}"
    )

    # Cria nota no Kommo (tenta; se falhar, ainda devolve a resposta)
    try:
        note_data = {
            "note_type": "common",
            "params": {"text": f"💬 Erika (IA TecBrilho): {resposta}"},
        }

        r = requests.post(
            f"{KOMMO_DOMAIN}/api/v4/leads/notes",
            headers={"Authorization": f"Bearer {KOMMO_TOKEN}"},
            json=note_data,
            timeout=30,
        )
        r.raise_for_status()
    except Exception as e:
        print(
            f"[{datetime.datetime.now()}] ERRO ao criar nota no Kommo "
            f"para lead_id={lead_id}: {e}"
        )
        return {
            "status": "ok",
            "lead_id": lead_id,
            "ai_response": resposta,
            "kommo_note": "failed",
            "error": str(e),
        }

    return {"status": "ok", "lead_id": lead_id, "ai_response": resposta}
