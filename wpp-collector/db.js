const { Pool } = require("pg");
const { knownIds, lastSeenAds } = require("./config");

const pool = new Pool({
  connectionString:
    process.env.DATABASE_URL ||
    "postgresql://postgres:postgres@localhost:5432/imoveis",
});

// ============================================================================
// INICIALIZAÇÃO DO ESTADO (Carrega histórico do PostgreSQL)
// ============================================================================
async function loadStateFromDB() {
  console.log("[DB] Loading PostgreSQL...");
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
  } catch (error) {
    console.error("[DB ERROR] Failed to load state from PostgreSQL:", error.message);
  }
}

module.exports = { pool, loadStateFromDB };
