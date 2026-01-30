const { Client, LocalAuth } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const SESSION_PATH = path.join(__dirname, "session");
const OUTPUT_FILE = path.join(__dirname, "messages.jsonl");
const DEDUP_WINDOW = 7776000;

const knownIds = new Set();
const lastSeenAds = new Map();

if (fs.existsSync(OUTPUT_FILE)) {
  const fileContent = fs.readFileSync(OUTPUT_FILE, "utf-8");
  fileContent.split("\n").forEach((line) => {
    if (line.trim()) {
      try {
        const parsed = JSON.parse(line);
        knownIds.add(parsed.message_id);
        if (parsed.ad_hash) {
          const key = `${parsed.author_id}_${parsed.ad_hash}`;
          if (
            !lastSeenAds.has(key) ||
            parsed.timestamp > lastSeenAds.get(key)
          ) {
            lastSeenAds.set(key, parsed.timestamp);
          }
        }
      } catch (e) {}
    }
  });
}

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
  qrcode.generate(qr, { small: true });
});

client.once("ready", () => {
  console.log("✓ Sentinela Ativo");
});

const generateHash = (text) => {
  return crypto
    .createHash("sha256")
    .update(text.toLowerCase().replace(/\s+/g, "").trim())
    .digest("hex");
};

client.on("message", async (message) => {
  try {
    if (!message.body || knownIds.has(message.id.id)) return;

    const chat = await message.getChat();
    if (!chat.isGroup) return;

    const authorId = message.author || message.from;
    const adHash = generateHash(message.body);
    const adKey = `${authorId}_${adHash}`;
    const now = Math.floor(Date.now() / 1000);

    if (lastSeenAds.has(adKey)) {
      const lastTimestamp = lastSeenAds.get(adKey);
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

    fs.appendFileSync(OUTPUT_FILE, JSON.stringify(payload) + "\n", {
      encoding: "utf-8",
    });
    knownIds.add(payload.message_id);
    lastSeenAds.set(adKey, payload.timestamp);

    console.log(
      `[CAPTURADO] ${payload.author_name}: ${payload.message.substring(0, 50)}`,
    );
  } catch (error) {
    console.error(error.message);
  }
});

client.initialize();
