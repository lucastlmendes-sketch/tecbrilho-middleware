// kommoChatClient.js
const crypto = require("crypto");
const fetch = global.fetch;

// Dados do canal de chat
const KOMMO_CHAT_SCOPE_ID = process.env.KOMMO_CHAT_SCOPE_ID; // scope_id do canal
const KOMMO_CHAT_BOT_ID = process.env.KOMMO_CHAT_BOT_ID;     // id do bot (sender.ref_id)
const KOMMO_CHAT_BOT_NAME = process.env.KOMMO_CHAT_BOT_NAME || "Erika";
const KOMMO_CHAT_API_SECRET = process.env.KOMMO_CHAT_API_SECRET; // secret do canal para assinar requests

// Endpoint: https://amojo.kommo.com/v2/origin/custom/{scope_id}
const CHAT_API_URL = `https://amojo.kommo.com/v2/origin/custom/${KOMMO_CHAT_SCOPE_ID}`;

// Gera assinatura no formato exigido (ver docs do Kommo para detalhes)
function generateSignature({ method, date, body }) {
  // Simplificado: METHOD\nDate\n\n\nbody
  // Consulte a doc se quiser seguir a string exata.
  const stringToSign = `${method.toUpperCase()}\n${date}\n\n\n${body}`;
  return crypto.createHmac("sha1", KOMMO_CHAT_API_SECRET)
    .update(stringToSign)
    .digest("hex");
}

// Envia mensagem de texto como "bot" para o cliente
async function sendErikaMessageToChat({ conversationId, clientProfile, text }) {
  const now = new Date().toUTCString();

  const payload = {
    event_type: "new_message",
    payload: {
      timestamp: Math.floor(Date.now() / 1000),
      msec_timestamp: Date.now(),
      msgid: `erika-${Date.now()}`,
      conversation_id: conversationId,
      sender: {
        id: "erika-bot",
        name: KOMMO_CHAT_BOT_NAME,
        ref_id: KOMMO_CHAT_BOT_ID
      },
      receiver: {
        id: clientProfile.id,
        name: clientProfile.name,
        avatar: clientProfile.avatar || "",
        profile: {
          phone: clientProfile.phone,
          email: clientProfile.email || ""
        }
      },
      message: {
        type: "text",
        text
      },
      silent: false
    }
  };

  const body = JSON.stringify(payload);
  const signature = generateSignature({
    method: "POST",
    date: now,
    body
  });

  const res = await fetch(CHAT_API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Date: now,
      "X-Signature": signature
    },
    body
  });

  if (!res.ok) {
    console.error("Erro ao enviar mensagem via Chats API:", await res.text());
  }
}

module.exports = {
  sendErikaMessageToChat
};
