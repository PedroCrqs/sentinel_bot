const { Client, LocalAuth } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const SESSION_PATH = path.join(__dirname, "session");
const OUTPUT_FILE = path.join(__dirname, "../data/messages.jsonl");
const DEDUP_WINDOW = 7776000;
const BLOCKED_IDS = new Set(["37658826899485@lid", "228707713171512@lid"]);

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
          if (
            !lastSeenAds.has(parsed.ad_hash) ||
            parsed.timestamp > lastSeenAds.get(parsed.ad_hash)
          ) {
            lastSeenAds.set(parsed.ad_hash, parsed.timestamp);
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
    headless: true,
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

client.on("authenticated", () => {
  console.log("=".repeat(80));
  console.log("SENTINEL IN");
  console.log("=".repeat(80));
});

client.once("ready", () => {
  console.log("=".repeat(80));
  console.log("SENTINEL RUNNING");
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
});

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

    fs.appendFileSync(OUTPUT_FILE, JSON.stringify(payload) + "\n", {
      encoding: "utf-8",
    });

    knownIds.add(payload.message_id);
    lastSeenAds.set(adHash, payload.timestamp);

    console.log(
      `[CAPTURADO] ${payload.author_name}: ${payload.message.substring(0, 50)}`,
    );
    console.log("=".repeat(80));
  } catch (error) {
    console.error(error.message);
  }
});

client.initialize();
