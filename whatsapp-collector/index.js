const { Client, LocalAuth } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const SESSION_PATH = path.join(__dirname, "session");
const OUTPUT_FILE = path.join(__dirname, "messages.jsonl");

if (!fs.existsSync(SESSION_PATH)) {
  fs.mkdirSync(SESSION_PATH, { recursive: true });
}

const client = new Client({
  authStrategy: new LocalAuth({
    dataPath: SESSION_PATH,
  }),
  puppeteer: {
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
    ],
  },
});

client.on("qr", (qr) => {
  console.log("\nEscaneie o QR Code abaixo com o WhatsApp:\n");
  qrcode.generate(qr, { small: true });
});

client.on("ready", () => {
  console.log("O Sentinela acessou o WhatsApp com sucesso!");
});

client.on("auth_failure", (msg) => {
  console.error("Falha de autenticação:", msg);
});

client.on("disconnected", (reason) => {
  console.warn("Cliente desconectado:", reason);
});

function normalizeText(text) {
  return text
    .toLowerCase()
    .replace(/\s+/g, " ")
    .replace(/[^\p{L}\p{N}\s]/gu, "")
    .trim();
}

function generateHash(authorId, text) {
  return crypto
    .createHash("sha256")
    .update(authorId + "|" + text)
    .digest("hex");
}

const DEDUP_WINDOW_SECONDS = 120;
const dedupCache = new Map();

client.on("message", async (message) => {
  try {
    if (!message.body) return;

    const chat = await message.getChat();

    if (!chat.isGroup) return;

    const authorId = message.author || message.from;
    const normalizedText = normalizeText(message.body);
    const hash = generateHash(authorId, normalizedText);

    const now = Math.floor(Date.now() / 1000);

    for (const [key, ts] of dedupCache.entries()) {
      if (now - ts > DEDUP_WINDOW_SECONDS) {
        dedupCache.delete(key);
      }
    }

    if (dedupCache.has(hash)) {
      return;
    }

    dedupCache.set(hash, now);

    const contact = await message.getContact();

    const phone = contact.number || contact.id?.user || null;

    const payload = {
      message_id: message.id.id,
      group_id: chat.id._serialized,
      group_name: chat.name,
      author_id: message.author || message.from,
      author_name: contact.pushname || contact.name || "Desconhecido",
      message: message.body,
      author_phone: phone,
      timestamp: message.timestamp,
    };

    fs.appendFileSync(OUTPUT_FILE, JSON.stringify(payload) + "\n", {
      encoding: "utf-8",
    });

    console.log(
      `[${new Date(payload.timestamp * 1000).toISOString()}] ` +
        `[${payload.group_name}] ` +
        `${payload.author_name}: ${payload.message.substring(0, 80)}`,
    );
  } catch (error) {
    console.error("Erro ao processar mensagem:", error);
  }
});

client.initialize();
