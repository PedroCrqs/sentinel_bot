// ============================================================================
// PONTO DE ENTRADA — só carrega env, importa os módulos e inicia o bot
// ============================================================================
require("dotenv").config({
  path: require("path").resolve(__dirname, "../.env"),
});

const { startBot } = require("./client"); // client.js já importa e anexa o ingest.js

startBot();
