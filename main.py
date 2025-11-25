from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from google.oauth2 import service_account
from googleapiclient.discovery import build
import openai
import json
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OPENAI
openai.api_key = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")

# GOOGLE CALENDAR SETUP
SERVICE_ACCOUNT_INFO = json.loads(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"))
SCOPES = ["https://www.googleapis.com/auth/calendar"]

credentials = service_account.Credentials.from_service_account_info(
    SERVICE_ACCOUNT_INFO,
    scopes=SCOPES
)

calendar_service = build("calendar", "v3", credentials=credentials)

# ROTAS ----------------------------------------------------------

@app.post("/webhook_chat")
async def webhook_chat(request: Request):
    body = await request.json()

    phone = body.get("phone")
    message = body.get("message")
    thread_id = body.get("thread_id")  # Pode vir vazio

    # 1️⃣ THREAD
    if not thread_id:
        thread = openai.beta.threads.create()
        thread_id = thread.id

    # 2️⃣ REGISTRA MENSAGEM DO USUÁRIO
    openai.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=message
    )

    # 3️⃣ EXECUTA ASSISTANT
    run = openai.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID
    )

    # 4️⃣ AGUARDA RESPOSTA
    while True:
        run_status = openai.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id
        )
        if run_status.status == "completed":
            break

    # 5️⃣ PEGA MENSAGEM DO ASSISTENTE
    msgs = openai.beta.threads.messages.list(thread_id)
    assistant_msg = msgs.data[0].content[0].text.value

    return {
        "send": [
            {"type": "text", "value": assistant_msg}
        ],
        "variables": {
            "thread_id": thread_id
        }
    }

# ---------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
