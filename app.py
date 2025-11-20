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
# (USAMOS VARIAÇÕES DE NOMES PARA CASAR COM O QUE A ERIKA FALA)
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
    "SOLICITAR FEEDBACK ": 96677123,

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
            # em alguns tipos pode vir em outro campo. Simplificamos.
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

Você é a Erika, assistente da TecBrilho, integrada ao CRM Kommo por meio de um robô interno.

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
                # pega o primeiro bloco de texto
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
# RESPOSTA PARA O SALESBOT (RETURN_URL)
# -----------------------------------------------------------------------------

def chunk_text(text: str, max_len: int = 80) -> List[str]:
    """Divide o texto em pedaços de até max_len caracteres."""
    text = text.strip()
    if not text:
        return []

    chunks: List[str] = []
    current = ""

    for part in text.split("\n"):
        for word in part.split(" "):
            if not word:
                continue
            if len(current) + len(word) + 1 > max_len:
                if current:
                    chunks.append(current)
                current = word
            else:
                current = f"{current} {word}".strip()
        if current:
            chunks.append(current)
            current = ""

    if current:
        chunks.append(current)
    return chunks


def send_salesbot_reply(return_url: str, erika_response: Dict[str, Any]) -> None:
    """
    Envia o resultado para o Salesbot via return_url.
    Consultando a doc 'SalesBot widget block execution confirmation'.
    """
    reply_text = erika_response.get("reply_to_customer") or ""
    if not reply_text:
        reply_text = "Tive um probleminha técnico ao processar a resposta agora. Pode repetir a última mensagem?"

    # Quebra em pedaços de até 80 caracteres por causa da limitação do handler "show".
    chunks = chunk_text(reply_text, max_len=80)

    execute_handlers: List[Dict[str, Any]] = []
    for chunk in chunks:
        execute_handlers.append(
            {
                "handler": "show",
                "params": {
                    "type": "text",
                    "value": chunk,
                },
            }
        )

    payload = {
        "data": erika_response,  # inteiro, para o Salesbot poder usar {{json.*}} depois
        "execute_handlers": execute_handlers,
    }

    headers = kommo_headers()

    try:
        resp = requests.post(return_url, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info(f"Salesbot continuado com sucesso via return_url.")
    except Exception as e:
        logger.error(f"Erro ao chamar return_url do Salesbot: {e}")


# -----------------------------------------------------------------------------
# PROCESSAMENTO DO WEBHOOK widget_request
# -----------------------------------------------------------------------------

def validate_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """Valida o JWT vindo do Kommo (widget_request)."""
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


def process_widget_request(payload: Dict[str, Any]) -> None:
    """
    Lógica principal: chamada em background quando o webhook chega.
    """
    try:
        token = payload.get("token")
        data = payload.get("data", {}) or {}
        return_url = payload.get("return_url")

        if not token or not return_url:
            logger.error("Payload do webhook sem token ou return_url.")
            return

        jwt_payload = validate_jwt_token(token)
        if not jwt_payload:
            logger.error("JWT inválido. Abortando processamento.")
            return

        incoming_message = data.get("message", "").strip()
        lead_id_raw = data.get("lead") or data.get("lead_id")

        if not incoming_message:
            logger.warning("Webhook sem mensagem do cliente.")
            return

        if not lead_id_raw:
            logger.warning("Webhook sem lead id. A Erika ainda responde, mas não haverá notas/mudança de etapa.")
            lead_id = None
        else:
            try:
                lead_id = int(str(lead_id_raw))
            except ValueError:
                logger.error(f"lead_id inválido: {lead_id_raw}")
                lead_id = None

        notes_context = ""
        if lead_id is not None:
            notes_context = get_lead_notes(lead_id, limit=5)

        erika_json = call_erika(incoming_message, notes_context)
        if not erika_json:
            # Falha – devolve uma mensagem padrão curta
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
                # Força a etapa "Solicitar Atendimento Humano", mesmo que a Erika tenha esquecido no campo.
                move_lead_to_stage(lead_id, "Solicitar Atendimento Humano")

        # Por fim, devolve a resposta ao Salesbot
        send_salesbot_reply(return_url, erika_json)

    except Exception as e:
        logger.error(f"Erro inesperado em process_widget_request: {e}")


# -----------------------------------------------------------------------------
# ROTAS FLASK
# -----------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def root():
    return jsonify({"status": "ok", "message": "Kommo ↔ Erika middleware rodando."})


@app.route("/health", methods=["GET"])
def health():
    return "OK", 200


@app.route("/salesbot/webhook", methods=["POST"])
def salesbot_webhook():
    """
    Endpoint que o Salesbot chama no handler widget_request.

    A lógica pesada é jogada para uma thread em background, e aqui
    só devolvemos 200 rápido para não estourar o timeout de 2s
    mencionado na doc.
    """
    payload = request.get_json(silent=True) or {}
    logger.info(f"Webhook recebido do Salesbot: {json.dumps(payload)[:500]}")

    # Processa em background
    threading.Thread(target=process_widget_request, args=(payload,)).start()

    # Resposta rápida apenas para confirmar recebimento
    return jsonify({"status": "accepted"}), 200


# -----------------------------------------------------------------------------
# ENTRYPOINT LOCAL (para testes)
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)
