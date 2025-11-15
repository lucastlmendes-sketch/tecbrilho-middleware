// server.js
require("dotenv").config();
const express = require("express");
const crypto = require("crypto");
const { askErika } = require("./openaiClient");
const {
  getOrCreateLeadForPhone,
  updateLeadStage,
  addLeadNote
} = require("./kommoCrmClient");
const { sendErikaMessageToChat } = require("./kommoChatClient");

const app = express();

// Precisamos do rawBody para validar X-Signature do Chat API
app.use(
  "/webhook/kommo-chat",
  express.raw({ type: "*/*" })
);

// Para outros endpoints, JSON normal
app.use(express.json());

const KOMMO_CHAT_WEBHOOK_SECRET = process.env.KOMMO_CHAT_WEBHOOK_SECRET;

// Valida X-Signature (webhook v2 Chats API)
function isValidChatWebhookSignature(req) {
  const signature = req.header("X-Signature");
  if (!signature || !KOMMO_CHAT_WEBHOOK_SECRET) return false;

  const body = req.body; // buffer
  const expected = crypto
    .createHmac("sha1", KOMMO_CHAT_WEBHOOK_SECRET)
    .update(body)
    .digest("hex");

  return signature === expected;
}

// Healthcheck simples para o Render
app.get("/", (req, res) => {
  res.send("Kommo + Erika middleware rodando ✅");
});

/**
 * WEBHOOK DO NOVO MENU (Chats API Webhook v2)
 * URL sugerida: https://kommo-middleware.onrender.com/webhook/kommo-chat
 */
app.post("/webhook/kommo-chat", async (req, res) => {
  try {
    if (!isValidChatWebhookSignature(req)) {
      console.warn("Assinatura inválida no webhook de chat");
      return res.status(401).send("Invalid signature");
    }

    const json = JSON.parse(req.body.toString("utf8"));
    const msg = json.message;

    // Estrutura v2 de exemplo:
    // json.message.receiver.phone, json.message.message.text, etc. :contentReference[oaicite:5]{index=5}
    const clientPhone = msg.receiver?.phone;
    const clientName = msg.receiver?.name || "Cliente";
    const text = msg.message?.text || "";

    if (!clientPhone || !text) {
      console.log("Webhook sem telefone ou texto, ignorando.");
      return res.status(200).send("ok");
    }

    // Já responde 200 rápido (recomendado pelo Kommo)
    res.status(200).send("ok");

    // Prepara info pro Erika
    const conversationId = msg.conversation?.id;
    const clientProfile = {
      id: msg.receiver.id,
      name: clientName,
      phone: clientPhone,
      email: msg.receiver.email || "",
      avatar: ""
    };

    // 1) Lead (criar/recuperar) — por padrão, deixo createIfMissing = action.create_lead_if_missing
    // mas só posso saber isso depois de falar com a Erika.
    // Então passo "createIfMissing: true" num primeiro momento, porque no primeiro contato
    // geralmente queremos registrar o lead.
    const { leadId } = await getOrCreateLeadForPhone({
      phone: clientPhone,
      name: clientName,
      createIfMissing: true,
      sourceText: `WhatsApp - conversa automática Erika`
    });

    // 2) Pergunta para a Erika
    const { clientText, erikaAction } = await askErika({
      phone: clientPhone,
      messageText: text,
      leadInfo: {
        id: leadId,
        name: clientName
      }
    });

    // 3) Envia resposta da Erika para o cliente via WhatsApp (Chats API)
    if (clientText && conversationId) {
      await sendErikaMessageToChat({
        conversationId,
        clientProfile,
        text: clientText
      });
    }

    // 4) Aplica ERIKA_ACTION (etapa de funil e nota)
    if (erikaAction && leadId) {
      if (erikaAction.kommo_suggested_stage) {
        await updateLeadStage(leadId, erikaAction.kommo_suggested_stage);
      }

      if (erikaAction.summary_note) {
        await addLeadNote(leadId, erikaAction.summary_note);
      }
    }
  } catch (e) {
    console.error("Erro no webhook /webhook/kommo-chat:", e);
    // não dá pra responder aqui se já mandamos 200, então só loga.
  }
});

// Porta para o Render
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Servidor ouvindo na porta ${PORT}`);
});
