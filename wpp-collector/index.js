const { Client, LocalAuth } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const SESSION_PATH = path.join(__dirname, "session");
const OUTPUT_FILE = path.join(__dirname, "messages.jsonl");
const DEDUP_WINDOW_SECONDS = 120;

const dedupCache = new Map();

if (!fs.existsSync(SESSION_PATH)) {
  fs.mkdirSync(SESSION_PATH, { recursive: true });
}

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: SESSION_PATH }),
  puppeteer: {
    headless: false,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
    ],
  },
});

client.on("qr", (qr) => {
  console.log("\nEscaneie o QR Code:\n");
  qrcode.generate(qr, { small: true });
});

client.once("ready", () => {
  console.log("\n✓ WhatsApp conectado");
  console.log("✓ Coletando mensagens de grupos");
  console.log("✓ Arquivo:", OUTPUT_FILE, "\n");
});

client.on("auth_failure", (msg) => {
  console.error("Erro de autenticação:", msg);
});

client.on("disconnected", (reason) => {
  console.warn("Desconectado:", reason);
});

const normalizeText = (text) =>
  text
    .toLowerCase()
    .replace(/\s+/g, " ")
    .replace(/[^\p{L}\p{N}\s]/gu, "")
    .trim();

const generateHash = (authorId, text) =>
  crypto
    .createHash("sha256")
    .update(authorId + "|" + text)
    .digest("hex");

client.on("message", async (message) => {
  try {
    if (!message.body) return;

    const chat = await message.getChat();
    if (!chat.isGroup) return;

    const authorId = message.author || message.from;
    const hash = generateHash(authorId, normalizeText(message.body));
    const now = Math.floor(Date.now() / 1000);

    for (const [key, ts] of dedupCache.entries()) {
      if (now - ts > DEDUP_WINDOW_SECONDS) dedupCache.delete(key);
    }

    if (dedupCache.has(hash)) return;
    dedupCache.set(hash, now);

    const contact = await message.getContact();
    const phone = contact.number || contact.id?.user || null;

    const payload = {
      message_id: message.id.id,
      group_id: chat.id._serialized,
      group_name: chat.name,
      author_id: authorId,
      author_name: contact.pushname || contact.name || "Desconhecido",
      author_phone: phone,
      message: message.body,
      timestamp: message.timestamp,
    };

    fs.appendFileSync(OUTPUT_FILE, JSON.stringify(payload) + "\n", {
      encoding: "utf-8",
    });

    console.log(
      `[${new Date(payload.timestamp * 1000).toISOString()}] ` +
        `[${payload.group_name}] ` +
        `${payload.author_name}: ${payload.message.substring(0, 50)}`,
    );
  } catch (error) {
    console.error("Erro:", error.message);
  }
});

client.initialize();
