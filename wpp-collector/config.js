// ============================================================================
// CONFIGURAÇÕES GERAIS
// ============================================================================
const path = require("path");
const fs = require("fs");

const SESSION_PATH = path.join(__dirname, "session");
const DEDUP_WINDOW = 7776000; // 90 dias

// Carrega os IDs bloqueados de uma variável de ambiente (separados por vírgula)
// Ex no .env: BLOCKED_IDS=37658826899485@lid,228707713171512@lid
// IDs dos grupos que não devem ser coletados
const blockedIdsArray = process.env.BLOCKED_IDS
  ? process.env.BLOCKED_IDS.split(",")
  : [];
const BLOCKED_IDS = new Set(blockedIdsArray);

// Estado em memória, compartilhado entre db.js (carga inicial) e ingest.js (atualização)
const knownIds = new Set();
const lastSeenAds = new Map();

if (!fs.existsSync(SESSION_PATH)) {
  fs.mkdirSync(SESSION_PATH, { recursive: true });
}

module.exports = {
  SESSION_PATH,
  DEDUP_WINDOW,
  BLOCKED_IDS,
  knownIds,
  lastSeenAds,
};
