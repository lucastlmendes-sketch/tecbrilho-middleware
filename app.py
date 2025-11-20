import os
import json
import logging
import threading
from typing import Dict, Any, List, Optional

import requests
import jwt
from flask import Flask, request, jsonify
from openai import OpenAI

# -----------------------------------------------------------------------------
# CONFIGURAÇÃO BÁSICA
# -----------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kommo-middleware")

app = Flask(__name__)

# OpenAI / Erika
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_ASSISTANT_ID = os.environ.get("OPENAI_ASSISTANT_ID", "")

if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY não configurado.")
if not OPENAI_ASSISTANT_ID:
    logger.warning("OPENAI_ASSISTANT_ID não configurado.")

openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Kommo
KOMMO_SUBDOMAIN = os.environ.get("KOMMO_SUBDOMAIN", "").strip()
KOMMO_BASE_URL = f"https://{KOMMO_SUBDOMAIN}.kommo.com" if KOMMO_SUBDOMAIN else None

KOMMO_LONG_LIVED_TOKEN = os.environ.get("KOMMO_LONG_LIVED_TOKEN", "")
KOMMO_CLIENT_SECRET = os.environ.get("KOMMO_CLIENT_SECRET", "")
KOMMO_INTEGRATION_ID = os.environ.get("KOMMO_INTEGRATION_ID", "")

if not KOMMO_BASE_URL:
    logger.warning("KOMMO_SUBDOMAIN não configurado.")
if not KOMMO_LONG_LIVED_TOKEN:
    logger.warning("KOMMO_LONG_LIVED_TOKEN não configurado.")
if not KOMMO_CLIENT_SECRET:
    logger.warning("KOMMO_CLIENT_SECRET não configurado.")


def kommo_headers() -> Dict[str, str]:
    """Cabeçalhos padrão para chamadas na API v4 da Kommo."""
    return {
        "Authorization": f"Bearer {KOMMO_LONG_LIVED_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# -----------------------------------------------------------------------------
# MAPA DE ETAPAS DO FUNIL (NOME → ID)
# -----------------------------------------------------------------------------

STAGE_NAME_TO_ID: Dict[str, int] = {
    # 1
    "ETAPA DE LEADS DE ENTRADA": 96505963,
    "LEADS RECEBIDOS": 96505963,

    # 2
    "CONTATO EM ANDAMENTO": 96505967,

    # 3
    "SERVIÇO VENDIDO": 96505971,
    "SERVICO VENDIDO": 96505971,

    # 4
    "AGENDAMENTO PENDENTE": 96505975,

    # 5
    "AGENDAMENTOS CONFIRMADOS": 96505979,

    # 6
    "CLIENTE PRESENTE": 96677111,

    # 7
    "CLIENTE AUSENTE": 96677115,

    # 8
    "REENGAJAR": 96677119,

    # 9
    "SOLICITAR FEEDBACK": 96677123,

    # 10
    "SOLICITAR AVALIAÇÃO NO GOOGLE": 96677127,
    "SOLICITAR AVALIACAO NO GOOGLE": 96677127,

    # 11
    "AVALIAÇÃO 5 ESTRELAS": 96677131,
    "AVALIACAO 5 ESTRELAS": 96677131,

    # 12
    "CLIENTE INSATISFEITO": 96677135,

    # 13
    "SOLICITAR ATENDIMENTO HUMANO": 96677139,

    # 14
    "FECHADO - GANHO": 142,
    "FECHADO GANHO": 142,

    # 15
    "FECHADO - PERDIDO": 143,
    "FECHADO PERDIDO": 143,
}


def normalize_stage_name(name: str) -> str:
    """Normaliza nome de etapa para bater com nosso dicionário."""
    return name.strip().upper()


# -----------------------------------------------------------------------------
# FUNÇÕES AUXILIARES – NOTAS E ETAPA NO KOMMO
# -----------------------------------------------------------------------------

def get_lead_notes(lead_id: int, limit: int = 5) -> str:
    """
    Busca as últimas notas da negociação no Kommo e devolve um texto
    curto para servir de contexto para a Erika.
    """
    if not KOMMO_BASE_URL:
        return ""

    url = f"{KOMMO_BASE_URL}/api/v4/leads/{lead_id}/notes"
    params = {"limit": limit, "order[created_at]": "desc"}

    try:
        resp = requests.get(url, headers=kommo_headers(), params=params, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Erro ao buscar notas do lead {lead_id}: {e}")
        return ""

    data = resp.json()
    embedded = data.get("_embedded", {})
    notes = embedded.get("notes", [])

    summaries: List[str] = []
    for note in notes:
        note_type = note.get("note_type", "common")
        params_note = note.get("params", {}) or {}
        text = params_note.get("text")
        if not text:
            text = json.dumps(params_note, ensure_ascii=False)
        summaries.append(f"- ({note_type}) {text}")

    if not summaries:
        return ""

    result = "\n".join(summaries)
    # Limita tamanho pra não estourar o prompt
    return result[:2000]


def add_lead_note(lead_id: int, text: str) -> None:
    """Adiciona uma nota comum ao lead."""
    if not KOMMO_BASE_URL or not text:
        return

    url = f"{KOMMO_BASE_URL}/api/v4/leads/notes"
    payload = [
        {
            "entity_id": lead_id,
            "note_type": "common",
            "params": {"text": text},
        }
    ]

    try:
        resp = requests.post(url, headers=kommo_headers(), json=payload, timeout=10)
        resp.raise_for_status()
        logger.info(f"Nota adicionada ao lead {lead_id}.")
    except Exception as e:
        logger.error(f"Erro ao adicionar nota ao lead {lead_id}: {e}")


def move_lead_to_stage(lead_id: int, stage_name: str) -> Optional[int]:
    """Atualiza a etapa da negociação, se o nome existir no mapa."""
    if not KOMMO_BASE_URL:
        return None

    if not stage_name:
        return None

    stage_id = STAGE_NAME_TO_ID.get(normalize_stage_name(stage_name))
    if not stage_id:
        logger.warning(f"Etapa '{stage_name}' não encontrada no mapa, ignorando.")
        return None

    url = f"{KOMMO_BASE_URL}/api/v4/leads/{lead_id}"
    payload = {"status_id": stage_id}

    try:
        resp = requests.patch(url, headers=kommo_headers(), json=payload, timeout=10)
        resp.raise_for_status()
        logger.info(f"Lead {lead_id} movido para etapa '{stage_name}' (id {stage_id}).")
        return stage_id
    except Exception as e:
        logger.error(f"Erro ao mover lead {lead_id} para etapa {stage_name}: {e}")
        return None


# -----------------------------------------------------------------------------
# CHAMANDO A ERIKA (ASSISTANTS API) COM JSON
# -----------------------------------------------------------------------------

JSON_INSTRUCTIONS = """
INSTRUÇÕES EXTRAS PARA FORMATO DE RESPOSTA:

Você é a Erika, assistente da TecBrilho, integrada ao CRM Kommo via webhook de chat.

Além de todas as suas regras já configuradas no painel da OpenAI, você DEVE responder
SEMPRE em JSON válido, com este formato exato (sem texto fora do JSON):

{
  "reply_to_customer": "mensagem em português, no tom e estilo da Erika, para enviar ao cliente no WhatsApp.",
  "kommo_stage": "nome exato da etapa do funil no Kommo, ou \"\" se não for mudar a etapa agora.",
  "kommo_note_summary": "resumo curto (1-3 frases) do que foi combinado ou discutido, para registrar como nota no lead.",
  "kommo_action": "none | move_stage | ask_human",
  "kommo_metadata": {
    "reason": "explicação curta (opcional) da ação tomada, por exemplo: motivo de pedir atendimento humano."
  }
}

Regras:
- Se você apenas responder dúvidas e não for necessário mudar etapa, use:
  "kommo_action": "none" e "kommo_stage": "".
- Se o cliente avançou claramente no funil (por exemplo, serviço fechado, agendamento definido, etc.),
  use "kommo_action": "move_stage" e preencha "kommo_stage" com o NOME da etapa
  exatamente como está no Kommo (por exemplo: "Contato em Andamento",
  "Serviço Vendido", "Agendamento Pendente", "Agendamentos Confirmados",
  "Cliente Presente", "Cliente Ausente", "Reengajar", "Solicitar Feedback",
  "Solicitar Avaliação no Google", "Avaliação 5 Estrelas", "Cliente Insatisfeito",
  "Solicitar Atendimento Humano", "Fechado - ganho", "Fechado - perdido" etc.).
- Sempre preencha "kommo_note_summary" com um resumo objetivo da conversa
  ou do próximo passo combinado (isso vira uma NOTA no lead dentro do Kommo).
- Se você detectar um caso complexo que precisa de humano (reclamação séria,
  exceção às regras comerciais, algo fora do escopo), use:
  "kommo_action": "ask_human" e "kommo_stage": "Solicitar Atendimento Humano",
  descrevendo na "kommo_metadata.reason" por que está pedindo atendimento humano.

NÃO escreva nada fora do JSON. Não use comentários. Não coloque crases ou markdown.
Apenas devolva um único objeto JSON.
"""


def build_erika_user_message(incoming_text: str, notes_context: str) -> str:
    """Monta a mensagem de usuário que será enviada para a Erika."""
    base = [
        "Contexto do CRM (resumo das últimas notas do lead):",
        notes_context if notes_context else "(sem notas anteriores relevantes).",
        "",
        "Mensagem atual do cliente (WhatsApp):",
        incoming_text,
        "",
        "Responda como Erika seguindo suas regras normais, "
        "mas lembre-se de que a resposta final deve estar no formato JSON descrito nas instruções extras.",
    ]
    return "\n".join(base)


def call_erika(incoming_text: str, notes_context: str) -> Dict[str, Any]:
    """
    Cria um thread, roda a Erika no modo Assistants API e espera um JSON.
    """
    if not OPENAI_API_KEY or not OPENAI_ASSISTANT_ID:
        logger.error("OpenAI não configurado corretamente.")
        return {}

    user_message = build_erika_user_message(incoming_text, notes_context)

    try:
        thread = openai_client.beta.threads.create(
            messages=[
                {
                    "role": "user",
                    "content": user_message,
                }
            ]
        )

        run = openai_client.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=OPENAI_ASSISTANT_ID,
            additional_instructions=JSON_INSTRUCTIONS,
            response_format={"type": "json_object"},
        )

        if run.status != "completed":
            logger.error(f"Run da Erika não completou: status={run.status}")
            return {}

        messages = openai_client.beta.threads.messages.list(thread_id=thread.id)
        # pega a última mensagem do assistente
        for msg in messages.data:
            if msg.role == "assistant":
                for content in msg.content:
                    if content.type == "text":
                        text_value = content.text.value.strip()
                        try:
                            data = json.loads(text_value)
                            return data
                        except Exception as e:
                            logger.error(f"Falha ao parsear JSON da Erika: {e} - texto='{text_value[:200]}'")
                            return {}
        return {}

    except Exception as e:
        logger.error(f"Erro ao chamar Erika: {e}")
        return {}


# -----------------------------------------------------------------------------
# ENVIO DE MENSAGEM PARA O CHAT (WHATSAPP) – /api/v4/chats/messages
# -----------------------------------------------------------------------------

def send_chat_message(conversation_id: str, text: str) -> None:
    """Envia mensagem de texto para o chat (WhatsApp) via API de chats da Kommo."""
    if not KOMMO_BASE_URL:
        logger.error("KOMMO_BASE_URL não configurado; não é possível enviar mensagem.")
        return

    if not conversation_id:
        logger.error("conversation_id vazio; não é possível enviar mensagem.")
        return

    text = (text or "").strip()
    if not text:
        logger.warning("Texto de resposta vazio; nada será enviado.")
        return

    url = f"{KOMMO_BASE_URL}/api/v4/chats/messages"
    payload = {
        "chat_id": conversation_id,
        "message_type": "text",
        "text": text,
    }

    try:
        resp = requests.post(url, headers=kommo_headers(), json=payload, timeout=10)
        resp.raise_for_status()
        logger.info(f"Mensagem enviada para chat {conversation_id}.")
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem para chat {conversation_id}: {e}")


# -----------------------------------------------------------------------------
# VALIDAÇÃO DO JWT DO WEBHOOK
# -----------------------------------------------------------------------------

def validate_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """Valida o JWT vindo do Kommo (header X-Signature ou campo token)."""
    if not token:
        return None

    if not KOMMO_CLIENT_SECRET:
        logger.warning("KOMMO_CLIENT_SECRET não configurado, NÃO validando JWT.")
        try:
            return jwt.decode(token, options={"verify_signature": False})
        except Exception:
            return None

    try:
        decoded = jwt.decode(
            token,
            KOMMO_CLIENT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        return decoded
    except Exception as e:
        logger.error(f"Falha ao validar JWT do Kommo: {e}")
        return None


# -----------------------------------------------------------------------------
# PROCESSAMENTO DO WEBHOOK DE CHAT
# -----------------------------------------------------------------------------

def process_chat_webhook(payload: Dict[str, Any], token: Optional[str]) -> None:
    """
    Lógica principal: chamada em background quando o webhook de chat chega.
    """
    try:
        if token:
            jwt_payload = validate_jwt_token(token)
            if not jwt_payload:
                logger.error("JWT inválido. Abortando processamento do webhook.")
                return
        else:
            logger.warning("Webhook recebido sem token/JWT. Prosseguindo sem validação de assinatura.")

        message = payload.get("message") or {}
        incoming_text = (message.get("text") or "").strip()
        conversation_id = message.get("conversation_id") or message.get("chat_id")

        if not incoming_text:
            logger.warning("Webhook de chat sem texto de mensagem.")
            return

        if not conversation_id:
            logger.error("Webhook sem conversation_id/chat_id; não há para onde responder.")
            return

        lead = payload.get("lead") or {}
        lead_id = lead.get("id")

        if lead_id is not None:
            try:
                lead_id = int(str(lead_id))
            except ValueError:
                logger.error(f"lead_id inválido: {lead_id}")
                lead_id = None

        notes_context = ""
        if lead_id is not None:
            notes_context = get_lead_notes(lead_id, limit=5)

        erika_json = call_erika(incoming_text, notes_context)
        if not erika_json:
            erika_json = {
                "reply_to_customer": "Encontrei um problema técnico aqui, mas já estou cuidando disso. "
                                     "Pode repetir a última mensagem ou tentar de novo em instantes? 😊",
                "kommo_stage": "",
                "kommo_note_summary": "",
                "kommo_action": "none",
                "kommo_metadata": {"reason": "fallback_erro_assistente"},
            }

        # Ações no Kommo: nota + mudança de etapa
        if lead_id is not None:
            note_text = erika_json.get("kommo_note_summary") or ""
            if note_text:
                note_full = f"[Erika IA]\n{note_text}"
                add_lead_note(lead_id, note_full)

            action = (erika_json.get("kommo_action") or "none").lower()
            if action == "move_stage":
                stage_name = erika_json.get("kommo_stage") or ""
                if stage_name:
                    move_lead_to_stage(lead_id, stage_name)
            elif action == "ask_human":
                move_lead_to_stage(lead_id, "Solicitar Atendimento Humano")

        reply_text = erika_json.get("reply_to_customer") or ""
        send_chat_message(conversation_id, reply_text)

    except Exception as e:
        logger.error(f"Erro inesperado em process_chat_webhook: {e}")


# -----------------------------------------------------------------------------
# ROTAS FLASK
# -----------------------------------------------------------------------------

@app.route("/chat/webhook", methods=["POST"])
def chat_webhook():
    try:
        print("\n=================== NOVO WEBHOOK RECEBIDO ===================")

        # Headers
        print("HEADERS:")
        for k, v in request.headers.items():
            print(f"{k}: {v}")

        # Query parameters
        print("\nQUERY PARAMS:")
        print(request.args.to_dict())

        # Body bruto
        raw = request.get_data(as_text=True)
        print("\nRAW BODY:")
        print(raw)

        # Tentativa de JSON
        try:
            json_body = request.get_json(force=True, silent=True)
            print("\nJSON PARSEADO:")
            print(json_body)
        except Exception as e:
            print("\nERRO AO PARSEAR JSON:", str(e))

        # Form-data
        print("\nFORM DATA:")
        print(request.form.to_dict())

        print("============================================================\n")

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print("ERRO NO WEBHOOK:", str(e))
        return "erro", 500


# -----------------------------------------------------------------------------
# ENTRYPOINT LOCAL (para testes)
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)
