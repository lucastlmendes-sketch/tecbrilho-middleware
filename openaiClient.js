// openaiClient.js
const OpenAI = require("openai");
const { splitErikaResponse } = require("./erikaParser");

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY
});

const ASSISTANT_ID = process.env.OPENAI_ASSISTANT_ID;

async function askErika({ phone, messageText, leadInfo }) {
  // Aqui você pode enriquecer a mensagem com contexto do lead se quiser
  const userContent = `
Telefone do cliente: ${phone}
Mensagem do cliente: ${messageText}
Informações atuais do lead: ${JSON.stringify(leadInfo || {}, null, 2)}
`.trim();

  // 1. cria thread
  const thread = await openai.beta.threads.create({
    messages: [
      {
        role: "user",
        content: userContent
      }
    ]
  });

  // 2. roda o assistant
  const run = await openai.beta.threads.runs.createAndPoll(
    thread.id,
    {
      assistant_id: ASSISTANT_ID
    }
  );

  if (run.status !== "completed") {
    throw new Error("Run da Erika não completou. Status: " + run.status);
  }

  // 3. pega última mensagem da Erika
  const messages = await openai.beta.threads.messages.list(thread.id);
  const lastAssistantMsg = messages.data.find(
    (m) => m.role === "assistant"
  );

  const fullText = lastAssistantMsg.content
    .map((c) => (c.type === "text" ? c.text.value : ""))
    .join("\n")
    .trim();

  const { clientText, action } = splitErikaResponse(fullText);

  return {
    clientText,
    erikaAction: action
  };
}

module.exports = { askErika };
