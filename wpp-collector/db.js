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
  console.log("[DB] Carregando histórico de mensagens do PostgreSQL...");
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
      `[DB] Histórico carregado. ${knownIds.size} mensagens em cache para deduplicação.`
    );
  } catch (error) {
    console.error("[DB ERRO] Falha ao carregar estado inicial:", error.message);
  }
}

module.exports = { pool, loadStateFromDB };
