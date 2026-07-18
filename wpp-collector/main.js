require("dotenv").config({ path: require('path').resolve(__dirname, '../.env') });
const { Client, LocalAuth } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { Pool } = require("pg");

// ============================================================================
// CONFIGURAÇÃO DO BANCO DE DADOS
// ============================================================================
const pool = new Pool({
  user: process.env.DB_USER || "postgres",
  host: process.env.DB_HOST || "localhost",
  database: process.env.DB_NAME || "sentinel_db",
  password: process.env.DB_PASSWORD || "admin",
  port: process.env.DB_PORT || 5432,
});

// ============================================================================
// CONFIGURAÇÕES GERAIS
// ============================================================================
const SESSION_PATH = path.join(__dirname, "session");
const DEDUP_WINDOW = 7776000; // 90 dias

// Carrega os IDs bloqueados de uma variável de ambiente (separados por vírgula)
// Ex no .env: BLOCKED_IDS=37658826899485@lid,228707713171512@lid
const blockedIdsArray = process.env.BLOCKED_IDS ? process.env.BLOCKED_IDS.split(",") : [];
const BLOCKED_IDS = new Set(blockedIdsArray);

const knownIds = new Set();
const lastSeenAds = new Map();

if (!fs.existsSync(SESSION_PATH)) {
  fs.mkdirSync(SESSION_PATH, { recursive: true });
}

// ============================================================================
// INICIALIZAÇÃO DO ESTADO (Carrega histórico do PostgreSQL)
// ============================================================================
async function loadStateFromDB() {
  console.log("[DB] Carregando histórico de mensagens do PostgreSQL...");
  try {
    const res = await pool.query("SELECT message_id, ad_hash, timestamp FROM raw_messages");
    
    res.rows.forEach((row) => {
      knownIds.add(row.message_id);
      
      if (row.ad_hash) {
        if (!lastSeenAds.has(row.ad_hash) || row.timestamp > lastSeenAds.get(row.ad_hash)) {
          lastSeenAds.set(row.ad_hash, Number(row.timestamp));
        }
      }
    });
    console.log(`[DB] Histórico carregado. ${knownIds.size} mensagens em cache para deduplicação.`);
  } catch (error) {
    console.error("[DB ERRO] Falha ao carregar estado inicial:", error.message);
  }
}

// ============================================================================
// CLIENTE WHATSAPP
// ============================================================================
const client = new Client({
  authStrategy: new LocalAuth({ dataPath: SESSION_PATH }),
  executablePath: process.env.CHROME_BIN || "/usr/bin/chromium", // Evita hardcode de SO
  puppeteer: {
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-extensions",
      "--no-first-run",
      "--disable-gpu",
      "--disable-software-rasterizer",
    ],
  },
});

async function startBot() {
  try {
    await loadStateFromDB(); // Carrega o estado ANTES de ligar o WhatsApp
    console.log("Starting WhatsApp client...");
    await client.initialize();
  } catch (err) {
    console.error(`[COLLECTOR] Initialization failed: ${err.message}. Retrying in 30s...`);
    setTimeout(startBot, 30000);
  }
}

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
  console.log("SENTINEL RUNNING (Connected to PostgreSQL)");
  console.log("=".repeat(80));
});

client.on("disconnected", (reason) => {
  console.log("=".repeat(80));
  console.warn("DISCONECTED:", reason);
  console.log("=".repeat(80));
});

client.on("auth_failure", (msg) => {
  console.log("=".repeat(80));
  console.error("AUTH FAILURE:", msg);
  console.log("=".repeat(80));
  setTimeout(startBot, 30000);
});

// ============================================================================
// PROCESSAMENTO DE MENSAGENS E INGESTÃO NO BANCO
// ============================================================================
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

client.on("message", async (message) => {
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
      payload.timestamp
    ];

    await pool.query(insertQuery, values);

    // Atualiza o cache em memória após salvar com sucesso
    knownIds.add(payload.message_id);
    lastSeenAds.set(adHash, payload.timestamp);

    console.log(`[POSTGRES] Ingerido -> ${payload.author_name}: ${payload.message.substring(0, 50)}...`);
    console.log("-".repeat(80));

  } catch (error) {
    console.error("[ERRO PROCESSAMENTO]", error.message);
  }
});

startBot();