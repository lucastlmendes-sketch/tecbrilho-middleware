# TecBrilho – Middleware de Agendamentos  
Integração entre BotConversa → Assistente OpenAI (Erika Agenda) → Google Calendar

Este middleware recebe dados do BotConversa via Webhook,
envia ao Assistente Erika Agenda (OpenAI) e retorna uma mensagem de
confirmação já formatada para o cliente.

O Assistente Agenda realiza:
- validação de horários  
- validação de capacidade  
- conversão de datas/horas  
- cálculo de duração  
- criação do evento no Google Calendar  
- geração da mensagem final  
- tudo internamente (Arquitetura A)

O backend só envia dados e devolve a resposta.

---

## 📌 Arquitetura Final

