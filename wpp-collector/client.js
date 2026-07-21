// ============================================================================
// CLIENTE WHATSAPP
// ============================================================================
const { Client, LocalAuth } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const { SESSION_PATH } = require("./config");
const { loadStateFromDB } = require("./db");
const { handleMessage } = require("./ingest");

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: SESSION_PATH }),
  webVersionCache: {
    type: "remote",
    remotePath:
      "https://raw.githubusercontent.com/wppconnect-team/wa-version/main/html/2.3000.1014589918-alpha.html", // Força uma versão estável e mantida pela comunidade atualizada
  },
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
    console.error(
      `[COLLECTOR] Initialization failed: ${err.message}. Retrying in 30s...`
    );
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
  console.warn("DISCONNECTED:", reason);
  console.log("=".repeat(80));
});

client.on("auth_failure", (msg) => {
  console.log("=".repeat(80));
  console.error("AUTH FAILURE:", msg);
  console.log("=".repeat(80));
  setTimeout(startBot, 30000);
});

client.on("message", handleMessage);

module.exports = { client, startBot };
