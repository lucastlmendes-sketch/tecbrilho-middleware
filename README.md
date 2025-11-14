# Kommo ↔ Erika IA (Chatbot Privado) – Middleware (Render)

Este projeto conecta o **Kommo** à assistente **Erika (OpenAI)** via API.
Ele foi pensado para funcionar com a **integração de *Private Chatbot* do Kommo** (SalesBot + widget privado).

- O **SalesBot** chama o widget.
- O widget envia a mensagem do cliente para este middleware (`/erika-chat`).
- O middleware chama a **Erika** (Assistants API).
- A resposta volta para o SalesBot, que responde no **WhatsApp / chat**.
- Opcionalmente a Erika:
  - registra **notas resumidas** no lead;
  - move o lead entre as **etapas do funil**.

> Importante: a resposta completa enviada ao cliente **não é mais gravada em nota**,
> apenas o **resumo técnico** definido pela Erika em `ERIKA_ACTION`.

---

## 🚀 Deploy (via GitHub + Render)

1. Crie/atualize um repositório no GitHub com:
   - `app.py`
   - `requirements.txt`
   - `render.yaml`
   - este `README.md`

2. No Render:
   - Clique em **New → Web Service → Git Provider** e conecte ao repositório.
   - Confirme:
     - **Build Command:** `pip install -r requirements.txt`
     - **Start Command:** `uvicorn app:app --host 0.0.0.0 --port 10000`

3. Em **Environment Variables**, configure pelo menos:

   - `OPENAI_API_KEY` – chave da API da OpenAI.
   - `OPENAI_ASSISTANT_ID` – ID da Erika (Assistants).
   - `KOMMO_DOMAIN` – domínio completo do Kommo (ex: `https://suaempresa.kommo.com`).
   - `KOMMO_TOKEN` – token de acesso à API do Kommo (Bearer token).

   Opcional:

   - `AUTHORIZED_SUBDOMAIN` – se definido, o middleware só atende requisições desse subdomínio.
   - IDs de etapas do funil (status_id) do Kommo:
     - `KOMMO_STATUS_LEADS_RECEBIDOS`
     - `KOMMO_STATUS_CONTATO_EM_ANDAMENTO`
     - `KOMMO_STATUS_SERVICO_VENDIDO`
     - `KOMMO_STATUS_AGENDAMENTO_PENDENTE`
     - `KOMMO_STATUS_AGENDAMENTOS_CONFIRMADOS`
     - `KOMMO_STATUS_CLIENTE_PRESENTE`
     - `KOMMO_STATUS_CLIENTE_AUSENTE`
     - `KOMMO_STATUS_REENGAJAR`
     - `KOMMO_STATUS_SOLICITAR_FEEDBACK`
     - `KOMMO_STATUS_SOLICITAR_AVALIACAO_GOOGLE`
     - `KOMMO_STATUS_AVALIACAO_5_ESTRELAS`
     - `KOMMO_STATUS_CLIENTE_INSATISFEITO`
     - `KOMMO_STATUS_VAGAS_DE_EMPREGO`
     - `KOMMO_STATUS_SOLICITAR_ATENDIMENTO_HUMANO`

4. Deploy. A URL pública ficará algo como:

   `https://kommo-middleware.onrender.com`

---

## 🔗 Endpoint usado pelo Chatbot Privado

O widget privado do Kommo deve apontar para:

```text
POST https://kommo-middleware.onrender.com/erika-chat
