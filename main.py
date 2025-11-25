import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import datetime
import google.oauth2.service_account
from googleapiclient.discovery import build

app = Flask(__name__)
CORS(app)

# ==== OPENAI ====
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")

# ==== GOOGLE CALENDAR CONFIG ====
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")

creds = google.oauth2.service_account.Credentials.from_service_account_info(
    eval(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")),
    scopes=["https://www.googleapis.com/auth/calendar"]
)
calendar_service = build("calendar", "v3", credentials=creds)


# ============================================
#  FUNCTION - CRIAR EVENTO NO CALENDÁRIO
# ============================================
def create_calendar_event(date, time, client_name, phone):
    try:
        start_str = f"{date}T{time}:00"
        end_time = (datetime.datetime.fromisoformat(start_str) +
                    datetime.timedelta(hours=1)).isoformat()

        event_body = {
            "summary": f"Atendimento - {client_name}",
            "description": f"Telefone: {phone}",
            "start": {"dateTime": start_str, "timeZone": "America/Sao_Paulo"},
            "end": {"dateTime": end_time, "timeZone": "America/Sao_Paulo"},
        }

        event = calendar_service.events().insert(
            calendarId=GOOGLE_CALENDAR_ID,
            body=event_body
        ).execute()

        return event.get("htmlLink")

    except Exception as e:
        return None


# ============================================
#  WEBHOOK BOTCONVERSA
# ============================================
@app.route("/webhook_chat", methods=["POST"])
def webhook_chat():
    try:
        body = request.json

        phone = body.get("phone")
        user_message = body.get("message")
        thread_id = body.get("thread_id")  # = contact.id

        if not thread_id:
            thread_id = phone.replace("+", "")

        # cria thread caso não exista
        try:
            thread = client.beta.threads.retrieve(thread_id=thread_id)
        except:
            thread = client.beta.threads.create(id=thread_id)

        # envia mensagem do usuário
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_message
        )

        # roda o assistente
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID
        )

        # espera finalizar
        while True:
            status = client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )
            if status.status in ["completed", "failed"]:
                break

        # =======================
        #  VERIFICAR FUNCTION CALL
        # =======================
        messages = client.beta.threads.messages.list(thread_id=thread.id)

        for msg in messages.data:
            if msg.role == "assistant" and msg.content[0].type == "function_call":
                fn = msg.content[0].function_call
                if fn.name == "create_calendar_event":
                    args = eval(fn.arguments)

                    event_link = create_calendar_event(
                        args["date"],
                        args["time"],
                        args["client_name"],
                        phone
                    )

                    resposta = f"Prontinho! Seu horário foi reservado 🤝\n\n📅 Dia: {args['date']}\n⏰ Horário: {args['time']}\n🔗 Confirmação: {event_link}"

                    return jsonify({
                        "send": [{"type": "text", "value": resposta}],
                        "variables": {"erika_resposta": resposta}
                    })

        # =======================
        #  RESPOSTA NORMAL
        # =======================
        assistant_msg = ""

        for msg in messages.data:
            if msg.role == "assistant" and msg.content[0].type == "text":
                assistant_msg = msg.content[0].text.value
                break

        if not assistant_msg:
            assistant_msg = "Desculpa, não consegui entender. Pode repetir? 😊"

        return jsonify({
            "send": [{"type": "text", "value": assistant_msg}],
            "variables": {"erika_resposta": assistant_msg}
        })

    except Exception as e:
        return jsonify({
            "send": [{
                "type": "text",
                "value": "Tivemos um probleminha técnico agora, mas já estou voltando! 🙏"
            }],
            "variables": {"erika_resposta": str(e)}
        })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
