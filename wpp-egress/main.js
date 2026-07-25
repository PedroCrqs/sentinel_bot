const fs = require("fs");
const path = require("path");
const qrcode = require("qrcode-terminal");
const { Client, LocalAuth } = require("whatsapp-web.js");
const { Pool } = require("pg");
const amqplib = require("amqplib"); // <-- NOVO: Biblioteca do RabbitMQ

// Aponta para o arquivo .env na raiz do projeto
require("dotenv").config({ path: path.resolve(__dirname, '../.env') });

// Configuração do RabbitMQ
const RABBITMQ_URL = process.env.RABBITMQ_URL || "amqp://localhost";

// Configuração do Pool de Conexão com o PostgreSQL
const pool = new Pool({
  connectionString:
    process.env.DATABASE_URL ||
    "postgresql://postgres:postgres@localhost:5432/imoveis",
});

const SESSION_PATH = path.join(__dirname, "session");

const GROUP_ID = "120363424642701935@g.us";
// Imóveis próprios: notificação prioritária vai direto por DM, não pro grupo
const PRIORITY_CONTACT_ID = "96654279573661@lid";

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
  console.log("SENTINEL EGRESS RUNNING (RabbitMQ Worker)");
  console.log("=".repeat(80));
  
  // Inicia o consumidor do RabbitMQ em vez do polling no banco
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
// Consumidor Orientado a Eventos do RabbitMQ
// ============================================================================
async function startRabbitMQConsumer() {
  try {
    const connection = await amqplib.connect(RABBITMQ_URL);
    const channel = await connection.createChannel();
    
    await channel.assertQueue("opportunities_queue", { durable: true });
    
    // Garante que o worker processe apenas 1 envio por vez para respeitar o rate-limit do WhatsApp
    channel.prefetch(1); 

    console.log("🐰 [RABBITMQ] Escutando a fila 'opportunities_queue'...");

    channel.consume("opportunities_queue", async (msg) => {
      if (msg !== null) {
        const payload = JSON.parse(msg.content.toString());
        const oppId = payload.opportunity_id;

        try {
          // Busca os detalhes da oportunidade recém-criada direto no banco
          const res = await pool.query(
            "SELECT match_details FROM opportunities WHERE opportunity_id = $1",
            [oppId]
          );

          if (res.rows.length > 0) {
            const opp = res.rows[0].match_details;
            
            // Mantendo o prefixo original
            const prefix = "⭐ *IMÓVEL PRÓPRIO*";
            const wppMessage = `${prefix}\n\n${format(opp)}`;

            // Dispara o WhatsApp (No momento para o GROUP_ID)
            await client.sendMessage(GROUP_ID, wppMessage);
            console.log(`[EGRESS] Oportunidade ${oppId} despachada instantaneamente via RabbitMQ!`); 

            // Atualiza o banco para SENT
            await pool.query(
              "UPDATE opportunities SET dispatch_status = 'SENT' WHERE opportunity_id = $1",
              [oppId]
            );
          }

          // Confirma o sucesso para o RabbitMQ deletar a mensagem da fila
          channel.ack(msg);
          
          // Mantém a pausa de 2 segundos de segurança para o WhatsApp
          await new Promise((resolve) => setTimeout(resolve, 2000));

        } catch (error) {
          console.error(`[EGRESS ERRO] Falha ao enviar oportunidade ${oppId}:`, error.message);
          // O `nack` (negative acknowledgement) com requeue=true devolve a mensagem para a fila tentar de novo
          channel.nack(msg, false, true); 
        }
      }
    });

  } catch (error) {
    console.error("❌ [RABBITMQ] Erro no consumidor do Egress:", error);
  }
}

function format(o) {
  // A estrutura 'o' agora reflete o retorno do Cypher salvo na coluna match_details
  const buyer = o.buyer || {};
  const seller = o.seller || {};

  let message = `🔥 *OPORTUNIDADE* | Score: ${o.score || 0}\n`;
  message += `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n`;

  message += `👤 *COMPRADOR*\n`;
  message += `Nome: ${buyer.name || "Não informado"}\n`;
  message += `Telefone: ${buyer.phone || "Não informado"}\n`;
  message += `\nTexto original:\n_${buyer.raw_text || "Sem texto"}_\n`;

  message += `\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n`;

  message += `🏢 *VENDEDOR*\n`;
  message += `Nome: ${seller.name || "Não informado"}\n`;
  message += `Telefone: ${seller.phone || "Não informado"}\n`;
  message += `\nTexto original:\n_${seller.raw_text || "Sem texto"}_`;

  return message;
}

client.initialize();