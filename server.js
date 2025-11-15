// ================================
// SERVER.JS – Middleware TecBrilho
// Compatível com Chat API v2
// ================================

require("dotenv").config();
const express = require("express");
const crypto = require("crypto");

// Módulos auxiliares
const { askErika } = require("./openaiClient");
const { 
  getOrCreateLeadForPhone, 
  updateLeadStage, 
  addLeadNote 
} = require("./kommoCrmClient");

const { 
  sendErikaMessageToChat 
} = require("./kommoChatClient");

const app = express();

// ================================
// MIDDLEWARE PARA RAW BODY (Chat API exige isso)
// ================================
app.use(
  "/kommo/chat-webhook",
  express.raw({ type: "*/*" })  // NÃO remover
);

// Outras rotas usam JSON normal:
app.use(express.json());


// ================================
// VALIDAÇÃO DA ASSINATURA DO WEBHOOK (X-Signature)
// ================================
const WEBHOOK_SECRET = process.env.KOMMO_CHAT_WEBHOOK_SECRET;

function isValidChatWebhookSignature(req) {
  const signature = req.headers["x-signature"];
  if (!signature) return false;

  if (!WEBHOOK_SECRET) {
    console.error("❌ Faltando KOMMO_CHAT_WEBHOOK_SECRET no Render");
    return false;
  }

  const expected = crypto
    .createHmac("sha1", WEBHOOK_SECRET)
    .update(req.body)
    .digest("hex");

  return signature === expected;
}


// ================================
// ROTA PRINCIPAL DO CHAT API (Webhook)
// ================================
app.post("/kommo/chat-webhook", async (req, res) => {
  try {
    // 1) Validar webhook
    if (!isValidChatWebhookSignature(req)) {
      console.warn("⚠️ Webhook rejeitado: assinatura inválida");
      return res.status(401).send("Invalid signature");
    }

    // 2) Parsear JSON manualmente (raw → string → JSON)
    const data = JSON.parse(req.body.toString("utf8"));

    const msg = data.message;
    if (!msg) {
      console.log("Webhook ignorado: sem mensagem");
      return res.status(200).send("ok");
    }

    const text = msg.message?.text || "";
    const phone = msg.receiver?.phone || "";
    const name = msg.receiver?.name || "Cliente";
    const conversationId = msg.conversation?.id;

    // Retornar rápido para o Kommo (obrigatório)
    res.status(200).send("ok");

    if (!text || !phone || !conversationId) {
      console.log("Mensagem ignorada: dados insuficientes");
      return;
    }

    // ================================
    // 3) Garantir um lead existente
    // ================================
    const { leadId } = await getOrCreateLeadForPhone({
      phone,
      name,
      createIfMissing: true,
      sourceText: "WhatsApp via Erika"
    });

    // ================================
    // 4) Enviar para Erika (OpenAI)
    // ================================
    const { clientText, erikaAction } = await askErika({
      phone,
      messageText: text,
      leadInfo: { id: leadId, name }
    });

    // ================================
    // 5) Responder cliente no WhatsApp via Chats API
    // ================================
    await sendErikaMessageToChat({
      conversationId,
      clientProfile: {
        id: msg.receiver.id,
        name,
        phone
      },
      text: clientText
    });

    // ================================
    // 6) Aplicar ações técnicas do ERIKA_ACTION no Kommo
    // ================================
    if (erikaAction && leadId) {
      if (erikaAction.kommo_suggested_stage) {
        await updateLeadStage(leadId, erikaAction.kommo_suggested_stage);
      }

      if (erikaAction.summary_note) {
        await addLeadNote(leadId, erikaAction.summary_note);
      }
    }

  } catch (e) {
    console.error("❌ Erro no webhook:", e);
  }
});


// ================================
// HEALTHCHECK PARA O RENDER
// ================================
app.get("/", (req, res) => {
  res.send("🚀 TecBrilho Middleware rodando com sucesso!");
});


// ================================
// INICIAR SERVIDOR
// ================================
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`🔥 Servidor iniciado na porta ${PORT}`);
});
