const { Pool } = require("pg");
const { knownIds, lastSeenAds } = require("./config");

const pool = new Pool({
  connectionString:
    process.env.DATABASE_URL ||
    "postgresql://postgres:CHANGE_ME@localhost:5432/sentinel_db",
});

// ============================================================================
// INICIALIZAÇÃO DO ESTADO (Carrega histórico do PostgreSQL)
// ============================================================================
async function loadStateFromDB(maxRetries = 5, retryDelayMs = 5000) {
  console.log("[DB] Loading PostgreSQL...");
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const res = await pool.query(
        "SELECT message_id, ad_hash, timestamp FROM raw_messages"
      );

      res.rows.forEach((row) => {
        knownIds.add(row.message_id);

        if (row.ad_hash) {
          if (
            !lastSeenAds.has(row.ad_hash) ||
            row.timestamp > lastSeenAds.get(row.ad_hash)
          ) {
            lastSeenAds.set(row.ad_hash, Number(row.timestamp));
          }
        }
      });
      console.log(
        `[DB] Story donwloaded. ${knownIds.size} messages in cache for deduplication.`
      );
      return;
    } catch (error) {
      console.error(
        `[DB ERROR] Failed to load state from PostgreSQL (attempt ${attempt}/${maxRetries}):`,
        error.message
      );
      if (attempt < maxRetries) {
        await new Promise((resolve) => setTimeout(resolve, retryDelayMs));
      }
    }
  }
}

module.exports = { pool, loadStateFromDB };
