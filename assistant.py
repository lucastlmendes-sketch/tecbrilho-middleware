
import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")


def send_to_erika(user_message: str, thread_id: str | None = None):
    """Envia mensagem para a Erika (Assistant) e retorna resposta + thread_id."""

    if not ASSISTANT_ID:
        raise RuntimeError("OPENAI_ASSISTANT_ID não configurado no ambiente.")

    if thread_id is None:
        thread = client.beta.threads.create()
        thread_id = thread.id

    # Mensagem do usuário
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_message,
    )

    # Execução do assistant
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID,
    )

    # Aguardar conclusão
    while True:
        run = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id,
        )
        if run.status in ("completed", "failed", "cancelled", "expired"):
            break

    if run.status != "completed":
        raise RuntimeError(f"Run da Erika não completou. Status: {run.status}")

    # Última mensagem (normalmente a resposta da Erika)
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    last = messages.data[0]

    textos = [
        part.text.value
        for part in last.content
        if part.type == "text"
    ]
    resposta = "\n".join(textos).strip()

    return resposta, thread_id
