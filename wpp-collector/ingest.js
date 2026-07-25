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

// Handler puro: recebe a mensagem do evento "message" do client e a processa.
// Não conhece o client — só sabe o que fazer com uma mensagem recebida.
async function handleMessage(message) {
  try {
    if (!message.body || knownIds.has(message.id.id)) return;

    const chat = await message.getChat();
    if (!chat.isGroup) return;

    const authorId = message.author || message.from;
    if (BLOCKED_IDS.has(authorId)) return;

    const adHash = generateHash(message.body);
    const now = Math.floor(Date.now() / 1000);

    // Lógica de Janela de Deduplicação (Permite o mesmo anúncio após 90 dias)
    if (lastSeenAds.has(adHash)) {
      const lastTimestamp = lastSeenAds.get(adHash);
      if (now - lastTimestamp < DEDUP_WINDOW) return;
    }

    const contact = await message.getContact();

    const payload = {
      message_id: message.id.id,
      group_id: chat.id._serialized,
      group_name: chat.name,
      author_id: authorId,
      author_name: contact.pushname || contact.name || "Desconhecido",
      author_phone: contact.number || contact.id?.user || null,
      message: message.body,
      ad_hash: adHash,
      timestamp: message.timestamp,
    };

    // Ingestão no PostgreSQL em vez de gravar no arquivo JSONL
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
      `[POSTGRES] Ingerido -> ${payload.author_name}: ${payload.message.substring(0, 50)}...`
    );
    console.log("-".repeat(80));
  } catch (error) {
    console.error("[ERRO PROCESSAMENTO]", error.message);
  }
}

module.exports = { handleMessage };
