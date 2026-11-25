// ============================================================================
// CLIENTE WHATSAPP
// ============================================================================
const fs = require("fs");
const path = require("path");
const { Client, LocalAuth } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const { SESSION_PATH } = require("./config");
const { loadStateFromDB } = require("./db");
const { handleMessage } = require("./ingest");
const { initRabbitMQ } = require("./rabbitmq");

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: SESSION_PATH }),
  // Desativa o cache local de HTML (./.wwebjs_cache/) para sempre usar o WhatsApp Web
  // atual e evitar EACCES silencioso no callback pós-autenticação
  webVersionCache: {
    type: "none",
  },
  puppeteer: {
    headless: true,
    ...(process.env.PUPPETEER_EXECUTABLE_PATH || fs.existsSync("/usr/bin/chromium")
      ? { executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || "/usr/bin/chromium" }
      : {}),
    protocolTimeout: Number(process.env.PUPPETEER_PROTOCOL_TIMEOUT_MS) || 300_000,
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

const AUTH_READY_TIMEOUT_MS =
  Number(process.env.AUTH_READY_TIMEOUT_MS) || 120_000;
const RESTART_DELAY_MS = 30_000;

let isClientReady = false;
let servicesInitialized = false;
let authReadyWatchdog = null;
let restartTimer = null;
let lastPageError = null;
const monitoredPages = new WeakSet();

function cleanStaleSessionLocks() {
  const sessionDir = path.join(SESSION_PATH, "session");
  for (const lockFile of ["SingletonLock", "SingletonSocket", "SingletonCookie"]) {
    try {
      fs.rmSync(path.join(sessionDir, lockFile), { force: true });
    } catch {}
  }
}

function clearAuthReadyWatchdog() {
  if (authReadyWatchdog) {
    clearTimeout(authReadyWatchdog);
    authReadyWatchdog = null;
  }
}

/**
 * Destrói o cliente atual com segurança e agenda uma única tentativa de
 * reinicialização, evitando reinícios concorrentes ou locks órfãos do Chromium.
 */
async function scheduleRestart(reason) {
  clearAuthReadyWatchdog();
  if (restartTimer) return;

  console.error(
    `[COLLECTOR] ${reason}. Retrying in ${Math.round(RESTART_DELAY_MS / 1000)}s...`
  );
  try {
    await client.destroy();
  } catch {}

  restartTimer = setTimeout(() => {
    restartTimer = null;
    startBot();
  }, RESTART_DELAY_MS);
}

/**
 * Monitora exceções não tratadas na página do Chromium (incluindo rejeições de
 * callbacks expostos via Puppeteer `exposeFunction`, como `onAppStateHasSyncedEvent`),
 * que normalmente ficam restritas ao contexto do browser e travariam o bot em silêncio.
 */
function attachPageErrorDiagnostics() {
  const page = client.pupPage;
  if (!page || monitoredPages.has(page)) return;
  monitoredPages.add(page);

  page.on("pageerror", (err) => {
    const detail = err?.message || String(err);
    lastPageError = detail;
    console.error(`[COLLECTOR] [Chromium pageerror] ${detail}`);

    if (!isClientReady && /EACCES|EROFS|ENOSPC|ready timeout/i.test(detail)) {
      scheduleRestart(
        `Critical error during post-auth load: ${detail}`
      );
    }
  });
}

/**
 * Watchdog pós-autenticação: se `authenticated` disparar mas `ready` não chegar
 * dentro de AUTH_READY_TIMEOUT_MS, destrói o Chromium e agenda reinicialização.
 */
function armAuthReadyWatchdog() {
  if (isClientReady || authReadyWatchdog) return;

  authReadyWatchdog = setTimeout(() => {
    authReadyWatchdog = null;
    if (isClientReady) return;

    const extra = lastPageError
      ? ` | Last pageerror: ${lastPageError}`
      : "";
    scheduleRestart(
      `Session authenticated, but "ready" event did not fire within ${Math.round(AUTH_READY_TIMEOUT_MS / 1000)}s${extra}`
    );
  }, AUTH_READY_TIMEOUT_MS);
}

async function startBot() {
  clearAuthReadyWatchdog();
  isClientReady = false;
  lastPageError = null;
  try {
    if (!servicesInitialized) {
      await loadStateFromDB(); // Carrega o estado ANTES de ligar o WhatsApp
      await initRabbitMQ(); // Inicia o RabbitMQ
      servicesInitialized = true;
    }
    cleanStaleSessionLocks();
    console.log("Starting WhatsApp client...");
    await client.initialize();
    attachPageErrorDiagnostics();
  } catch (err) {
    await scheduleRestart(`Initialization failed: ${err.message}`);
  }
}

client.on("qr", (qr) => {
  qrcode.generate(qr, { small: true });
});

client.on("authenticated", () => {
  attachPageErrorDiagnostics();
  console.log("=".repeat(80));
  console.log("SENTINEL IN");
  console.log("=".repeat(80));
  armAuthReadyWatchdog();
});

client.on("ready", () => {
  isClientReady = true;
  clearAuthReadyWatchdog();
  attachPageErrorDiagnostics();
  console.log("=".repeat(80));
  console.log("SENTINEL RUNNING (Connected to PostgreSQL)");
  console.log("=".repeat(80));
});

client.on("disconnected", (reason) => {
  isClientReady = false;
  clearAuthReadyWatchdog();
  console.log("=".repeat(80));
  console.warn("DISCONNECTED:", reason);
  console.log("=".repeat(80));
});

client.on("auth_failure", async (msg) => {
  isClientReady = false;
  console.log("=".repeat(80));
  console.error("AUTH FAILURE:", msg);
  console.log("=".repeat(80));
  await scheduleRestart(`Auth failure: ${msg}`);
});

// Proteção para evitar erros e locks órfãos em encerramentos controlados
process.on("SIGTERM", async () => {
  clearAuthReadyWatchdog();
  if (restartTimer) {
    clearTimeout(restartTimer);
    restartTimer = null;
  }
  console.log("[COLLECTOR] SIGTERM received — shutting down gracefully");
  try {
    await client.destroy();
  } catch {}
  process.exit(0);
});

client.on("message", handleMessage);

module.exports = { client, startBot };
