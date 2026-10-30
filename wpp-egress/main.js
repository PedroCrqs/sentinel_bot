const fs = require("fs");
const path = require("path");
const qrcode = require("qrcode-terminal");
const { Client, LocalAuth } = require("whatsapp-web.js");
const { Pool } = require("pg");
const amqplib = require("amqplib");

// Aponta para o arquivo .env na raiz do projeto
require("dotenv").config({ path: path.resolve(__dirname, "../.env") });

// Configuração do RabbitMQ
const RABBITMQ_URL = process.env.RABBITMQ_URL || "amqp://localhost:5672";

// Configuração do Pool de Conexão com o PostgreSQL
const pool = new Pool({
  connectionString:
    process.env.DATABASE_URL ||
    "postgresql://postgres:CHANGE_ME@localhost:5432/sentinel_db",
});

const SESSION_PATH = path.join(__dirname, "session");

// Destinatários
const GROUP_ID = process.env.GROUP_ID || "";
const PRIORITY_CONTACT_ID = process.env.PRIORITY_CONTACT_ID || "";

// Rate Limit para oportunidades de terceiros enviadas ao grupo
// Padrão: no máximo 10 mensagens por hora para não poluir o grupo
const MAX_GROUP_OPPS_PER_HOUR = parseInt(
  process.env.MAX_GROUP_OPPS_PER_HOUR || "10",
  10
);
const groupSentTimestamps = [];

if (!GROUP_ID) {
  console.warn(
    "⚠️ [CONFIG] GROUP_ID não configurado no .env. Mensagens para o grupo ficarão retidas."
  );
}

if (!PRIORITY_CONTACT_ID) {
  console.warn(
    "⚠️ [CONFIG] PRIORITY_CONTACT_ID não configurado no .env. Imóveis próprios usarão fallback para GROUP_ID se disponível."
  );
}

if (!fs.existsSync(SESSION_PATH)) {
  fs.mkdirSync(SESSION_PATH, { recursive: true });
}

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: SESSION_PATH }),
  puppeteer: {
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  },
});

client.on("qr", (qr) => {
  qrcode.generate(qr, { small: true });
});

client.on("authenticated", () => {
  console.log("=".repeat(80));
  console.log("SENTINEL IN");
  console.log("=".repeat(80));
});

client.once("ready", () => {
  console.log("=".repeat(80));
  console.log("SENTINEL EGRESS RUNNING (RabbitMQ Worker v2.0.0)");
  console.log("=".repeat(80));

  // Inicia o consumidor do RabbitMQ
  startRabbitMQConsumer();
});

client.on("disconnected", (reason) => {
  console.log("=".repeat(80));
  console.warn("DISCONNECTED:", reason);
  console.log("=".repeat(80));
});

client.on("auth_failure", (msg) => {
  console.log("=".repeat(80));
  console.error("AUTH FAILURE:", msg);
  console.log("=".repeat(80));
});

// ============================================================================
// Identificador estrito de Imóvel Próprio vs Imóvel de Terceiro
// ============================================================================
function isSelfOpportunity(opp) {
  if (opp.offer_id && String(opp.offer_id).startsWith("self-offer:")) {
    return true;
  }
  if (
    opp.seller &&
    opp.seller.name &&
    String(opp.seller.name).toLowerCase().includes("majesto")
  ) {
    return true;
  }
  return false;
}

// ============================================================================
// Formatação e Resolução de Números de Telefone
// ============================================================================
function formatPhoneNumber(phone) {
  if (!phone) return "Não informado";
  const digits = String(phone).replace(/\D/g, "");
  // Celular brasileiro completo com DDI: 5521999998888 (13 dígitos)
  if (digits.length === 13 && digits.startsWith("55")) {
    const ddd = digits.slice(2, 4);
    const p1 = digits.slice(4, 9);
    const p2 = digits.slice(9);
    return `+55 (${ddd}) ${p1}-${p2}`;
  }
  // Celular brasileiro com DDD: 21999998888 (11 dígitos)
  if (digits.length === 11) {
    const ddd = digits.slice(0, 2);
    const p1 = digits.slice(2, 7);
    const p2 = digits.slice(7);
    return `+55 (${ddd}) ${p1}-${p2}`;
  }
  // Fixo brasileiro com DDI: 552133334444 (12 dígitos)
  if (digits.length === 12 && digits.startsWith("55")) {
    const ddd = digits.slice(2, 4);
    const p1 = digits.slice(4, 8);
    const p2 = digits.slice(8);
    return `+55 (${ddd}) ${p1}-${p2}`;
  }
  // Se for LID não resolvido
  if (String(phone).includes("@lid") || digits.length > 13) {
    return `${phone} (ID WhatsApp)`;
  }
  return phone;
}

function getWhatsAppLink(phone) {
  if (!phone) return null;
  const digits = String(phone).replace(/\D/g, "");
  if (digits.length >= 10 && digits.length <= 13) {
    const full = digits.startsWith("55") ? digits : `55${digits}`;
    return `https://wa.me/${full}`;
  }
  return null;
}

async function resolvePhoneIfLid(phone, rawText) {
  // Se já for um telefone convencional
  if (phone && !String(phone).includes("@lid")) {
    const d = String(phone).replace(/\D/g, "");
    if (d.length >= 10 && d.length <= 13) return phone;
  }
  // Tenta extrair do texto original
  if (rawText) {
    const m = rawText.match(/(?:\+?55\s?)?(?:\(?([1-9]{2})\)?\s?)?(?:9\s?\d{4})[-\s]?(\d{4})\b/);
    if (m) {
      const d = m[0].replace(/\D/g, "");
      if (d.length === 9) return `5521${d}`;
      if (d.length === 11) return `55${d}`;
      if (d.length === 13) return d;
    }
  }
  // Tenta resolver via WhatsApp Web caso seja LID
  if (phone && client) {
    const lidId = String(phone).includes("@") ? String(phone) : `${phone}@lid`;
    try {
      if (typeof client.getContactLidAndPhone === "function") {
        const res = await client.getContactLidAndPhone(lidId);
        if (res && res[0] && res[0].pn) {
          return res[0].pn.split("@")[0];
        }
      }
    } catch (_) {}
  }
  return phone;
}

// ============================================================================
// Controle de Fluxo por Hora para o Grupo (Parcerias)
// ============================================================================
async function checkAndApplyGroupRateLimit() {
  const ONE_HOUR_MS = 60 * 60 * 1000;
  const now = Date.now();

  // Limpa registros mais antigos que 1 hora
  while (
    groupSentTimestamps.length > 0 &&
    now - groupSentTimestamps[0] >= ONE_HOUR_MS
  ) {
    groupSentTimestamps.shift();
  }

  // Se atingiu a cota máxima na última hora, aguarda a liberação da vaga mais antiga
  if (groupSentTimestamps.length >= MAX_GROUP_OPPS_PER_HOUR) {
    const oldestTimestamp = groupSentTimestamps[0];
    const waitTimeMs = ONE_HOUR_MS - (now - oldestTimestamp) + 1000;
    console.log(
      `⏳ [RATE LIMIT GRUPO] Limite de ${MAX_GROUP_OPPS_PER_HOUR} envios/hora atingido. Aguardando ${Math.ceil(
        waitTimeMs / 1000
      )}s para despachar o próximo...`
    );
    await new Promise((resolve) => setTimeout(resolve, waitTimeMs));
    return checkAndApplyGroupRateLimit();
  }

  groupSentTimestamps.push(Date.now());
}

// ============================================================================
// Consumidor Orientado a Eventos do RabbitMQ
// ============================================================================
async function startRabbitMQConsumer() {
  try {
    const connection = await amqplib.connect(RABBITMQ_URL);
    const channel = await connection.createChannel();

    await channel.assertQueue("opportunities_queue", { durable: true });
    channel.prefetch(1);

    console.log("🐰 [RABBITMQ] Escutando a fila 'opportunities_queue'...");

    channel.consume("opportunities_queue", async (msg) => {
      if (msg !== null) {
        const payload = JSON.parse(msg.content.toString());
        const oppId = payload.opportunity_id;

        try {
          // Busca os detalhes da oportunidade direto no banco
          const res = await pool.query(
            "SELECT match_details FROM opportunities WHERE opportunity_id = $1",
            [oppId]
          );

          if (res.rows.length > 0) {
            const opp = res.rows[0].match_details;
            const isSelf = isSelfOpportunity(opp);

            let destination = "";
            let logType = "";

            if (isSelf) {
              // Imóveis próprios Majesto: envio direto e prioritário na DM sem limite por hora
              destination = PRIORITY_CONTACT_ID || GROUP_ID;
              logType = "IMÓVEL PRÓPRIO MAJESTO (DM - SEM LIMITE)";
            } else {
              // Imóveis de parceiros (terceiros): vão para o grupo com limitador de taxa
              await checkAndApplyGroupRateLimit();
              destination = GROUP_ID;
              logType = "PARCERIA/TERCEIRO (GRUPO)";
            }

            if (!destination) {
              console.warn(
                `⚠️ [EGRESS] Destinatário não configurado para ${logType}. Oportunidade ${oppId} não enviada.`
              );
              channel.ack(msg);
              return;
            }

            // Enriquece e valida os telefones de comprador e vendedor
            if (opp.buyer) {
              opp.buyer.phone = await resolvePhoneIfLid(opp.buyer.phone, opp.buyer.raw_text);
            }
            if (opp.seller) {
              opp.seller.phone = await resolvePhoneIfLid(opp.seller.phone, opp.seller.raw_text);
            }

            const wppMessage = format(opp, isSelf);
            await client.sendMessage(destination, wppMessage);

            console.log(
              `✅ [EGRESS] Oportunidade ${oppId} [${logType}] enviada com sucesso para ${destination}!`
            );

            // Atualiza status no banco com os telefones enriquecidos
            await pool.query(
              "UPDATE opportunities SET dispatch_status = 'SENT', match_details = $1 WHERE opportunity_id = $2",
              [opp, oppId]
            );
          }

          // Confirmação para RabbitMQ
          channel.ack(msg);

          // Pausa de 2 segundos de segurança para o WhatsApp
          await new Promise((resolve) => setTimeout(resolve, 2000));
        } catch (error) {
          console.error(
            `❌ [EGRESS ERRO] Falha ao enviar oportunidade ${oppId}:`,
            error.message
          );
          channel.nack(msg, false, true);
        }
      }
    });
  } catch (error) {
    console.error("❌ [RABBITMQ] Erro no consumidor do Egress:", error);
  }
}

function format(o, isSelf) {
  const buyer = o.buyer || {};
  const seller = o.seller || {};

  const header = isSelf
    ? "⭐ *OPORTUNIDADE — IMÓVEL PRÓPRIO*"
    : "🔥 *OPORTUNIDADE DE PARCERIA*";

  let message = `${header} | Score: ${o.score || 0}\n`;
  message += `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n`;

  const buyerPhoneFormatted = formatPhoneNumber(buyer.phone);
  const buyerWaLink = getWhatsAppLink(buyer.phone);

  message += `👤 *COMPRADOR*\n`;
  message += `Nome: ${buyer.name || "Não informado"}\n`;
  message += `Telefone: ${buyerPhoneFormatted}\n`;
  if (buyerWaLink) {
    message += `WhatsApp: ${buyerWaLink}\n`;
  }
  message += `\nTexto original:\n_${buyer.raw_text || "Sem texto"}_\n`;

  message += `\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n`;

  if (isSelf) {
    message += `🏢 *VENDEDOR (INVENTÁRIO PRÓPRIO MAJESTO)*\n`;
    message += `Nome: Majesto (Imóvel Próprio)\n`;
    message += `Telefone: Base de Imóveis Majesto (Opção Direta)\n`;
    message += `\nTexto original:\n_${seller.raw_text || "Sem texto"}_`;
  } else {
    message += `🏢 *VENDEDOR (PARCEIRO)*\n`;
    message += `Nome: ${seller.name || "Não informado"}\n`;
    message += `Telefone: ${formatPhoneNumber(seller.phone)}\n`;
    const sellerWaLink = getWhatsAppLink(seller.phone);
    if (sellerWaLink) {
      message += `WhatsApp: ${sellerWaLink}\n`;
    }
    message += `\nTexto original:\n_${seller.raw_text || "Sem texto"}_`;
  }

  return message;
}

client.initialize();
