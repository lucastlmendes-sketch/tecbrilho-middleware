// kommoCrmClient.js
const fetch = global.fetch;

const KOMMO_DOMAIN = process.env.KOMMO_DOMAIN; // ex: https://tecbrilho.kommo.com
const KOMMO_TOKEN = process.env.KOMMO_TOKEN;

// Mapeia o nome da etapa (texto que vem do ERIKA_ACTION) para o ID do status
function mapStageNameToId(stageName) {
  if (!stageName) return null;

  const map = {
    "Leads Recebidos": process.env.KOMMO_STATUS_LEADS_RECEBIDOS,
    "Contato em Andamento": process.env.KOMMO_STATUS_CONTATO_EM_ANDAMENTO,
    "Serviço Vendido": process.env.KOMMO_STATUS_SERVICO_VENDIDO,
    "Agendamento Pendente": process.env.KOMMO_STATUS_AGENDAMENTO_PENDENTE,
    "Agendamentos Confirmados": process.env.KOMMO_STATUS_AGENDAMENTOS_CONFIRMADOS,
    "Cliente Presente": process.env.KOMMO_STATUS_CLIENTE_PRESENTE,
    "Cliente Ausente": process.env.KOMMO_STATUS_CLIENTE_AUSENTE,
    "Reengajar": process.env.KOMMO_STATUS_REENGAJAR,
    "Solicitar FeedBack": process.env.KOMMO_STATUS_SOLICITAR_FEEDBACK,
    "Solicitar Avaliação Google": process.env.KOMMO_STATUS_SOLICITAR_AVALIACAO_GOOGLE,
    "Avaliação 5 Estrelas": process.env.KOMMO_STATUS_AVALIACAO_5_ESTRELAS,
    "Cliente Insatisfeito": process.env.KOMMO_STATUS_CLIENTE_INSATISFEITO,
    "Vagas de Emprego": process.env.KOMMO_STATUS_VAGAS_DE_EMPREGO,
    "Solicitar Atendimento Humano": process.env.KOMMO_STATUS_SOLICITAR_ATENDIMENTO_HUMANO
  };

  return map[stageName] || null;
}

// Busca contato por telefone (query simples)
async function findContactByPhone(phone) {
  const url = `${KOMMO_DOMAIN}/api/v4/contacts?query=${encodeURIComponent(
    phone
  )}`;

  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${KOMMO_TOKEN}`,
      "Content-Type": "application/json",
      Accept: "application/json"
    }
  });

  if (!res.ok) {
    console.error("Erro ao buscar contato:", await res.text());
    return null;
  }

  const data = await res.json();
  return data._embedded?.contacts?.[0] || null;
}

// Busca leads ligados ao contato
async function getContactLeads(contactId) {
  const url = `${KOMMO_DOMAIN}/api/v4/contacts/${contactId}?with=leads`;

  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${KOMMO_TOKEN}`,
      "Content-Type": "application/json",
      Accept: "application/json"
    }
  });

  if (!res.ok) {
    console.error("Erro ao buscar leads do contato:", await res.text());
    return [];
  }

  const data = await res.json();
  return data._embedded?.leads || [];
}

// Cria lead + contato (complex)
async function createLeadWithContact({ name, phone, sourceText }) {
  const url = `${KOMMO_DOMAIN}/api/v4/leads/complex`;

  const body = [
    {
      name: sourceText || "Lead WhatsApp",
      _embedded: {
        contacts: [
          {
            name: name || phone,
            custom_fields_values: [
              {
                field_code: "PHONE",
                values: [{ value: phone }]
              }
            ]
          }
        ]
      }
    }
  ];

  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${KOMMO_TOKEN}`,
      "Content-Type": "application/json",
      Accept: "application/json"
    },
    body: JSON.stringify(body)
  });

  if (!res.ok) {
    console.error("Erro ao criar lead/contato:", await res.text());
    throw new Error("Erro ao criar lead/contato");
  }

  const data = await res.json();
  const created = data[0];
  return {
    leadId: created.id,
    contactId: created.contact_id
  };
}

// Retorna um lead para trabalhar (ou cria se precisar)
async function getOrCreateLeadForPhone({ phone, name, createIfMissing, sourceText }) {
  const contact = await findContactByPhone(phone);

  if (contact) {
    const leads = await getContactLeads(contact.id);
    if (leads.length > 0) {
      // pega o lead mais recente
      return { leadId: leads[0].id, contactId: contact.id, created: false };
    }
    // sem lead, mas contato existe → cria lead ligado a ele
    const { leadId } = await createLeadWithContact({
      name: contact.name,
      phone,
      sourceText
    });
    return { leadId, contactId: contact.id, created: true };
  }

  if (!createIfMissing) {
    return { leadId: null, contactId: null, created: false };
  }

  const { leadId, contactId } = await createLeadWithContact({
    name,
    phone,
    sourceText
  });
  return { leadId, contactId, created: true };
}

// Atualiza estágio do lead
async function updateLeadStage(leadId, stageName) {
  const statusId = mapStageNameToId(stageName);
  if (!statusId) return;

  const url = `${KOMMO_DOMAIN}/api/v4/leads`;

  const body = [
    {
      id: leadId,
      status_id: Number(statusId)
    }
  ];

  const res = await fetch(url, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${KOMMO_TOKEN}`,
      "Content-Type": "application/json",
      Accept: "application/json"
    },
    body: JSON.stringify(body)
  });

  if (!res.ok) {
    console.error("Erro ao atualizar estágio do lead:", await res.text());
  }
}

// Adiciona nota com resumo
async function addLeadNote(leadId, noteText) {
  if (!leadId || !noteText) return;

  const url = `${KOMMO_DOMAIN}/api/v4/leads/notes`;

  const body = [
    {
      entity_id: leadId,
      note_type: "common",
      params: {
        text: noteText
      }
    }
  ];

  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${KOMMO_TOKEN}`,
      "Content-Type": "application/json",
      Accept: "application/json"
    },
    body: JSON.stringify(body)
  });

  if (!res.ok) {
    console.error("Erro ao adicionar nota:", await res.text());
  }
}

module.exports = {
  getOrCreateLeadForPhone,
  updateLeadStage,
  addLeadNote
};
