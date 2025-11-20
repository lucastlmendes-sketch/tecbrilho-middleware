from flask import Flask, request, jsonify

app = Flask(__name__)

# Rota principal (Render usa para health check)
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "ok",
        "service": "tecbrilho-middleware-python"
    })

# Webhook da Kommo — ainda vazio, vamos implementar na Etapa 2
@app.route("/kommo/webhook", methods=["POST"])
def kommo_webhook():
    return jsonify({
        "status": "received"
    })

# Render inicia pela variável PORT
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
