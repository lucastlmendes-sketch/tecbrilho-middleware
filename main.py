import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI

app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")


@app.route("/webhook_chat", methods=["POST"])
def webhook_chat():
    try:
        data = request.get_json()

        # Dados enviados pelo BotConversa
        phone = data.get("phone")
        user_message = data.get("message")
        thread_id = data.get("thread_id")  # Agora vem de {{contact.id}}

        if not phone or not user_message:
            return jsonify({"error": "Campos obrigatórios ausentes."}), 400

        if not thread_id:
            # fallback seguro
            thread_id = phone.replace("+", "").replace("-", "")

        # Criar ou recuperar thread
        thread = client.beta.threads.retrieve(thread_id=thread_id) \
            if thread_id else client.beta.threads.create()
        
        # Enviar mensagem do usuário ao assistente
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_message
        )

        # Rodar o assistente
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID
        )

        # Aguardar conclusão
        while True:
            status = client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )
            if status.status in ["completed", "failed", "cancelled"]:
                break

        if status.status != "completed":
            return jsonify({
                "send": [{
                    "type": "text",
                    "value": "Tive um probleminha técnico aqui agora, mas já podemos tentar de novo em instantes, tudo bem? 🙏"
                }],
                "variables": {
                    "erika_resposta": "Erro ao gerar resposta",
                }
            })

        # Obter resposta do assistente
        messages = client.beta.threads.messages.list(thread_id=thread.id)
        assistant_msg = ""

        for msg in messages.data:
            if msg.role == "assistant":
                assistant_msg = msg.content[0].text.value
                break

        if not assistant_msg:
            assistant_msg = "Desculpa, não consegui entender. Pode repetir pra mim? 😊"

        # Resposta no formato BotConversa espera
        return jsonify({
            "send": [
                {
                    "type": "text",
                    "value": assistant_msg
                }
            ],
            "variables": {
                "erika_resposta": assistant_msg
            }
        })

    except Exception as e:
        return jsonify({
            "send": [{
                "type": "text",
                "value": "Tive um probleminha técnico aqui agora, mas já podemos tentar de novo em instantes, tudo bem? 🙏"
            }],
            "variables": {
                "erika_resposta": str(e)
            }
        })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
