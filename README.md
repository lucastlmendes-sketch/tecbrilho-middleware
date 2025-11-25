# TecBrilho Middleware

Middleware em Python (FastAPI) para integração entre:
- BotConversa (WhatsApp)
- OpenAI Assistant (Erika)
- Google Agenda (Service Account)
- Render (deploy)

## Endpoints

### `GET /`
Retorna o status do serviço.

### `POST /webhook_chat`
Recebe mensagem do BotConversa e retorna a resposta da Erika.

Exemplo de payload de entrada (ajuste de acordo com o BotConversa):

```json
{
  "message": "texto do cliente",
  "phone": "5511999999999",
  "thread_id": "opcional",
  "contactId": "id_do_contato"
}
```

Exemplo de resposta:

```json
{
  "send": [
    {
      "type": "text",
      "value": "Resposta da Erika"
    }
  ],
  "variables": {
    "thread_id": "id_da_thread",
    "nota": "resumo interno"
  }
}
```

### `POST /webhook_schedule`
Cria um evento no Google Agenda para o serviço agendado.

Exemplo de payload de entrada:

```json
{
  "cliente_nome": "João Silva",
  "telefone": "5511999999999",
  "veiculo_modelo": "Corolla 2018",
  "servico": "Polimento Comercial",
  "categoria": "polimentos",
  "data": "2025-11-24",
  "hora_inicio": "09:00",
  "duracao_minutos": 240,
  "resumo_conversa": "Resumo da negociação..."
}
```

## Variáveis de ambiente

Veja o arquivo `.env.example` para a lista completa
