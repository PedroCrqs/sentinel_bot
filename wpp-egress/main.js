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
// Identificador de Imóvel Próprio vs Imóvel de Terceiro
// ============================================================================
function isSelfOpportunity(opp) {
  if (opp.offer_id && String(opp.offer_id).startsWith("self-offer:")) {
    return true;
  }
  if (opp.matched_imovel_id !== null && opp.matched_imovel_id !== undefined) {
    return true;
  }
  if (
    opp.seller &&
    opp.seller.name &&
    String(opp.seller.name).includes("Majesto")
  ) {
    return true;
  }
  return false;
}

// ============================================================================
// Controle de Fluxo por Hora para o Grupo
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

            // ================================================================
            // NOTA / REFINAMENTO FUTURO: Filtro por Score Mínimo
            // Mantido comentado na v2.0.0 para não descartar matches em fase de teste.
            // const MIN_MATCH_SCORE_GROUP = 50;
            // if (!isSelf && (opp.score || 0) < MIN_MATCH_SCORE_GROUP) {
            //   console.log(`[EGRESS] Opp ${oppId} ignorada por score baixo: ${opp.score}`);
            //   channel.ack(msg);
            //   return;
            // }
            // ================================================================

            let destination = "";
            let logType = "";

            if (isSelf) {
              // Imóveis próprios: prioridade DM direta
              destination = PRIORITY_CONTACT_ID || GROUP_ID;
              logType = "IMÓVEL PRÓPRIO (DM)";
            } else {
              // Imóveis de parceiros: grupo de corretores com controle de taxa
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

            const wppMessage = format(opp, isSelf);
            await client.sendMessage(destination, wppMessage);

            console.log(
              `✅ [EGRESS] Oportunidade ${oppId} [${logType}] enviada com sucesso para ${destination}!`
            );

            // Atualiza status no banco
            await pool.query(
              "UPDATE opportunities SET dispatch_status = 'SENT' WHERE opportunity_id = $1",
              [oppId]
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

  message += `👤 *COMPRADOR*\n`;
  message += `Nome: ${buyer.name || "Não informado"}\n`;
  message += `Telefone: ${buyer.phone || "Não informado"}\n`;
  message += `\nTexto original:\n_${buyer.raw_text || "Sem texto"}_\n`;

  message += `\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n`;

  const sellerLabel = isSelf
    ? "🏢 *VENDEDOR (INVENTÁRIO PRÓPRIO MAJESTO)*"
    : "🏢 *VENDEDOR (PARCEIRO)*";

  message += `${sellerLabel}\n`;
  message += `Nome: ${seller.name || "Não informado"}\n`;
  message += `Telefone: ${seller.phone || "Não informado"}\n`;
  message += `\nTexto original:\n_${seller.raw_text || "Sem texto"}_`;

  return message;
}

client.initialize();
