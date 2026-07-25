const fs = require("fs");
const path = require("path");
const qrcode = require("qrcode-terminal");
const { Client, LocalAuth } = require("whatsapp-web.js");
const { Pool } = require("pg");

// Aponta para o arquivo .env na raiz do projeto
require("dotenv").config({ path: path.resolve(__dirname, '../.env') });

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
  console.log("SENTINEL RUNNING");
  console.log("=".repeat(80));
  // TEMP (v1.7.0): dispatch de oportunidades regulares em standby.
  // Só a notificação de imóveis próprios (dispatchSelfLoop) está ativa.
  // Para reativar: descomente a linha abaixo.
  // dispatchLoop();
  
  // Novo loop de dispatch integrado ao PostgreSQL
  dispatchDatabaseLoop();
});

// client.on("message", async (message) => {
//   const chat = await message.getChat();
//   if (chat.isGroup) {
//     console.log(`Grupo: ${chat.name}`);
//     console.log(`ID: ${chat.id._serialized}`);
//     console.log("=".repeat(80));
//   }
// });

client.on("disconnected", (reason) => {
  console.log("=".repeat(80));
  console.warn("DISCONECTED:", reason);
  console.log("=".repeat(80));
});

client.on("auth_failure", (msg) => {
  console.log("=".repeat(80));
  console.error("AUTH FAILURE:", msg);
  console.log("=".repeat(80));
});

async function dispatchDatabaseLoop() {
  try {
    // Busca até 5 oportunidades pendentes por vez no banco
    const res = await pool.query(
      "SELECT opportunity_id, match_details FROM opportunities WHERE dispatch_status = 'PENDING' ORDER BY created_at ASC LIMIT 5"
    );

    for (const row of res.rows) {
      const opp = row.match_details;
      
      // Mantendo o prefixo e o destino do dispatchSelfLoop original
      const prefix = "⭐ *IMÓVEL PRÓPRIO*";
      const msg = `${prefix}\n\n${format(opp)}`;

      await client.sendMessage(GROUP_ID, msg);
      console.log(`Sent (db_self): ${row.opportunity_id}`); 

      await pool.query(
      "UPDATE opportunities SET dispatch_status = 'SENT' WHERE opportunity_id = $1",
     [row.opportunity_id]
);
      // Pausa de 2 segundos entre envios, conforme o código original
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
  } catch (error) {
    console.error(`Dispatch error (database):`, error.message);
  }

  // Roda novamente a cada 5 segundos
  setTimeout(dispatchDatabaseLoop, 5000);
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
