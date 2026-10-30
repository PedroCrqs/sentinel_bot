// ============================================================================
// PROCESSAMENTO DE MENSAGENS E INGESTÃO NO BANCO
// ============================================================================
const crypto = require("crypto");
const { pool } = require("./db");
const { BLOCKED_IDS, DEDUP_WINDOW, knownIds, lastSeenAds } = require("./config");
const { publishRawMessageEvent } = require("./rabbitmq");

const normalizeText = (text) => {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[\p{Emoji_Presentation}\p{Extended_Pictographic}]/gu, "")
    .replace(/[^\w\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
};

const generateHash = (text) => {
  const normalized = normalizeText(text);
  return crypto.createHash("md5").update(normalized).digest("hex");
};

// Extração de telefone celular ou fixo brasileiro a partir do texto
function extractPhoneFromText(text) {
  if (!text) return null;
  // wa.me/5521999998888 or wa.me/21999998888
  const wameMatch = text.match(/wa\.me\/(?:55)?([1-9]{2}9?\d{8})/i);
  if (wameMatch) {
    const digits = wameMatch[1];
    return digits.length === 11 ? `55${digits}` : digits;
  }

  // Celular com DDD (21) 98888-7777, 21 98888-7777, 21988887777
  const cellMatch = text.match(/(?:\+?55\s?)?(?:\(?([1-9]{2})\)?\s?)?(?:9\s?\d{4})[-\s]?(\d{4})\b/);
  if (cellMatch) {
    const digits = cellMatch[0].replace(/\D/g, "");
    if (digits.length === 9) return `5521${digits}`;
    if (digits.length === 11) return `55${digits}`;
    if (digits.length === 13) return digits;
  }

  // Fixo ou 8 dígitos
  const landMatch = text.match(/(?:\+?55\s?)?(?:\(?([1-9]{2})\)?\s?)?(?:[2-5]\d{3})[-\s]?(\d{4})\b/);
  if (landMatch) {
    const digits = landMatch[0].replace(/\D/g, "");
    if (digits.length === 8) return `5521${digits}`;
    if (digits.length === 10) return `55${digits}`;
    if (digits.length === 12) return digits;
  }

  return null;
}

function isLid(val) {
  if (!val) return true;
  const str = String(val).trim();
  if (str.includes("@lid") || str.toLowerCase() === "desconhecido") return true;
  const digits = str.replace(/\D/g, "");
  return digits.length > 13 || digits.length < 10;
}

// Handler puro: recebe a mensagem do evento "message" do client e a processa.
async function handleMessage(message) {
  try {
    if (!message.body || knownIds.has(message.id.id)) return;

    const chat = await message.getChat();
    if (!chat.isGroup) return;

    const authorId = message.author || message.from;
    if (BLOCKED_IDS.has(authorId) || authorId === "237374353195087@lid") {
      return;
    }

    const adHash = generateHash(message.body);
    const now = Math.floor(Date.now() / 1000);

    // Lógica de Janela de Deduplicação (Permite o mesmo anúncio após 90 dias)
    if (lastSeenAds.has(adHash)) {
      const lastTimestamp = lastSeenAds.get(adHash);
      if (now - lastTimestamp < DEDUP_WINDOW) return;
    }

    const contact = await message.getContact();

    const authorNameCheck = (contact.pushname || contact.name || "").toLowerCase();
    if (authorNameCheck.includes("toledo") || authorNameCheck.includes("phelippe")) {
      return;
    }

    let authorPhone = null;

    // 1. Se authorId for @c.us, o user já é o telefone direto
    if (authorId && authorId.endsWith("@c.us")) {
      authorPhone = authorId.replace("@c.us", "");
    }

    // 2. Se contact.number for um telefone válido (não LID)
    if (!authorPhone && contact && contact.number && !isLid(contact.number)) {
      authorPhone = contact.number;
    }

    // 3. Se for @lid, tentar resolver o telefone real através do WhatsApp Web
    if ((!authorPhone || isLid(authorPhone)) && authorId && authorId.endsWith("@lid")) {
      try {
        if (message.client && typeof message.client.getContactLidAndPhone === "function") {
          const lidRes = await message.client.getContactLidAndPhone(authorId);
          if (lidRes && lidRes[0] && lidRes[0].pn) {
            authorPhone = lidRes[0].pn.split("@")[0];
          }
        }
      } catch (_) {}
    }

    // 4. Se ainda for LID ou nulo, extrai o telefone do corpo da mensagem
    if (!authorPhone || isLid(authorPhone)) {
      const fromText = extractPhoneFromText(message.body);
      if (fromText) {
        authorPhone = fromText;
      }
    }

    // Fallback final: se não foi possível resolver, mantém o ID do usuário
    if (!authorPhone) {
      authorPhone = contact.number || contact.id?.user || null;
    }

    const payload = {
      message_id: message.id.id,
      group_id: chat.id._serialized,
      group_name: chat.name,
      author_id: authorId,
      author_name: contact.pushname || contact.name || "Desconhecido",
      author_phone: authorPhone,
      message: message.body,
      ad_hash: adHash,
      timestamp: message.timestamp,
    };

    // Ingestão no PostgreSQL
    const insertQuery = `
      INSERT INTO raw_messages
      (message_id, group_id, group_name, author_id, author_name, author_phone, message, ad_hash, timestamp, status)
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'PENDING')
      ON CONFLICT (message_id) DO NOTHING;
    `;

    const values = [
      payload.message_id,
      payload.group_id,
      payload.group_name,
      payload.author_id,
      payload.author_name,
      payload.author_phone,
      payload.message,
      payload.ad_hash,
      payload.timestamp,
    ];

    await pool.query(insertQuery, values);

    // Atualiza o cache em memória após salvar com sucesso
    knownIds.add(payload.message_id);
    lastSeenAds.set(adHash, payload.timestamp);

    // Publica o evento no RabbitMQ
    publishRawMessageEvent(payload.message_id);

    console.log(
      `[POSTGRES] Ingerido -> ${payload.author_name} (Tel: ${payload.author_phone}): ${payload.message.substring(0, 50)}...`
    );
    console.log("-".repeat(80));
  } catch (error) {
    console.error("[ERRO PROCESSAMENTO]", error.stack || error.message || error);
  }
}

module.exports = { handleMessage };
