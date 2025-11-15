# Kommo + OpenAI (Assistant) — Middleware Oficial

Este projeto serve como **ponte entre o Kommo** (via *Private Chatbot Integration* / Salesbot) e o **Assistant da Erika** hospedado na API da OpenAI.

Ele é projetado para ser hospedado na **Render.com** e receber webhooks do Kommo via **widget_request**.

---

# 🚀 Funcionalidades

- Recebe mensagens do Salesbot (via bloco “Widget”).
- Envia para o **OpenAI Assistant** (modelo configurado via `OPENAI_ASSISTANT_ID`).
- Interpreta o retorno em dois blocos:
  - `---VISIBLE---` → texto final para o cliente
  - `---ERIKA_ACTION---` → ações estruturadas (JSON)
- Adiciona notas no lead do Kommo.
- Move o lead para outra etapa se houver recomendação da Erika.
- 🔄 Envia a resposta de volta para o Salesbot via `return_url` (obrigatório).

---

# 📁 Estrutura

