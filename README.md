# 🚀 TecBrilho Middleware – Integração BotConversa + OpenAI + Google Calendar

Este middleware conecta:

- **BotConversa** (via Webhook)  
- **Assistente Erika Agenda (OpenAI Assistants v2)**  
- **Google Calendar**  
- **FastAPI (Render)**  

Foi desenvolvido na **Arquitetura A — O Assistente Agenda faz TUDO**.

Ou seja:

✅ O BotConversa envia os dados via webhook  
✅ O middleware envia para o Assistente da OpenAI  
✅ O Assistente Agenda:
- valida horários  
- cria o evento no Google Calendar  
- monta mensagem final para o cliente  

✅ O middleware apenas retorna essa mensagem ao BotConversa  

Simples, escalável e extremamente estável.

---

# 📦 Estrutura dos Arquivos

