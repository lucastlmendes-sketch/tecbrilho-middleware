
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests, os, datetime

app = FastAPI(title="Kommo ↔ Alexandria Middleware (Zidane Integrated)")

# === Env vars ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
KOMMO_TOKEN = os.getenv("KOMMO_TOKEN")
KOMMO_DOMAIN = os.getenv("KOMMO_DOMAIN")  # ex.: https://tecnobrilho.kommo.com
ZIDANE_ASSISTANT_ID = os.getenv("ZIDANE_ASSISTANT_ID")  # opcional (usará fallback se não houver)

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
    return {"status": "ok", "message": "Middleware ativo (Zidane)", "kommo_domain": KOMMO_DOMAIN}

@app.get("/health")
def health():
    ok = bool(OPENAI_API_KEY and KOMMO_DOMAIN)
    return {"ok": ok, "timestamp": datetime.datetime.now().isoformat()}

@app.get("/ping")
def ping():
    return {"status": "alive", "ts": datetime.datetime.now().isoformat()}

# === Prompt fallback do Zidane (usado se nao houver Assistant ID) ===
ZIDANE_PROMPT = (
    "Você é Zidane, o Closer Premium da TecBrilho — especialista em estética automotiva. "
    "Objetivos: criar conexão, entender a demanda e conduzir para agendamento. "
    "Coletar: primeiro nome e sobrenome leve, modelo/ano do veículo; telefone apenas se não vier do WhatsApp. "
    "Pergunte o melhor dia/horário do cliente; se houver vaga, confirme; se não houver, use escassez com alternativa no mesmo dia. "
    "Fale com empatia, frases curtas e foco em valor ('acabamento impecável', 'brilho de vitrine', 'proteção profissional'). "
    "Evite falar de preço até o final; se insistir, ofereça Premium vs Essencial. "
    "Finalize com resumo breve e próximo passo claro."
)

def call_openai_zidane(user_message: str) -> str:
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    # 1) Tenta via Responses API com assistant_id (novo fluxo)
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
            # Extrai texto (estrutura do Responses API)
            if "output" in data and isinstance(data["output"], list):
                for item in data["output"]:
                    if item.get("type") == "message":
                        parts = item["message"].get("content", [])
                        for part in parts:
                            if part.get("type") == "output_text":
                                return part.get("text", "").strip()
            # Fallback simples se a estrutura variar
            return data.get("output_text") or "Não consegui extrair a resposta do assistente."
        except Exception as e:
            # Cai para chat completions
            pass

    # 2) Fallback estável: Chat Completions com prompt do Zidane
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
        return f"Erro ao gerar resposta: {e}"

# === Webhook Kommo ===
@app.post("/kommo-webhook")
async def kommo_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload inválido ou ausente")

    # Validação automática do subdomínio do Kommo
    subdomain = payload.get("account", {}).get("subdomain")
    if AUTHORIZED_SUBDOMAIN and subdomain != AUTHORIZED_SUBDOMAIN:
        raise HTTPException(status_code=401, detail=f"Subdomínio não autorizado: {subdomain}")

    print(f"[{datetime.datetime.now()}] Webhook recebido do subdomínio: {subdomain}")

    # Extrai mensagem e lead
    message = (
        payload.get("message", {}).get("text")
        or payload.get("text")
        or payload.get("last_message", {}).get("text")
        or ""
    )
    lead = payload.get("lead") or {}
    lead_id = lead.get("id") or payload.get("lead_id")

    if not message:
        return {"status": "ignored", "reason": "sem mensagem", "payload_keys": list(payload.keys())}

    # Chama a IA (Zidane)
    resposta = call_openai_zidane(message)

    # Cria nota no Kommo (tenta; se falhar, devolve mesmo assim)
    try:
        note_data = {"note_type": "common", "params": {"text": f"💬 Zidane: {resposta}"}}
        # Algumas contas exigem array; tentamos forma simples primeiro
        r = requests.post(
            f"{KOMMO_DOMAIN}/api/v4/leads/notes",
            headers={"Authorization": f"Bearer {KOMMO_TOKEN}"},
            json=note_data,
            timeout=30,
        )
        r.raise_for_status()
    except Exception as e:
        return {"status": "ok", "lead_id": lead_id, "ai_response": resposta, "kommo_note": "failed", "error": str(e)}

    return {"status": "ok", "lead_id": lead_id, "ai_response": resposta}
