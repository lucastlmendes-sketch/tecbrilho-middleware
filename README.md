TecBrilho Middleware - BotConversa + OpenAI Assistants + Google Calendar
=======================================================================

Arquivos todos na **raiz** do projeto:

- `main.py` – aplicação FastAPI (endpoint `/webhook_chat`)
- `config.py` – lê variáveis de ambiente
- `state_store.py` – guarda o `thread_id` por contato (arquivo JSON)
- `openai_client.py` – integração com o Assistente da OpenAI
- `calendar_client.py` – integração com Google Calendar
- `botconversa_client.py` – (por enquanto) apenas loga as tags
- `requirements.txt`
- `.env.example`

Comando para rodar localmente::

    uvicorn main:app --reload

No Render, use:

    Start command: uvicorn main:app --host 0.0.0.0 --port $PORT
