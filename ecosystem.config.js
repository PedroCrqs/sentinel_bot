const path = require("path");

// Configuração pm2 do Sentinel Bot.
// Uso:
//   pm2 start ecosystem.config.js   # inicia os três processos
//   pm2 save                        # persiste a lista atual de processos
//   pm2 startup                     # gera o comando pra iniciar o pm2 no boot do Debian
//
// Ver README.md > "Deploy 24/7 com pm2" para o passo a passo completo.

// Descobre se está rodando no Windows ou no Linux/Mac
const isWindows = process.platform === "win32";
const pythonPath = isWindows ? ["Scripts", "python.exe"] : ["bin", "python"];

module.exports = {
  apps: [
    {
      name: "sentinel-collector", // ingest: escuta o WhatsApp, salva no Postgres e emite evento no RabbitMQ
      script: "main.js",
      cwd: path.join(__dirname, "wpp-collector"),
      interpreter: "node",
      autorestart: true,
      max_restarts: 15,
      restart_delay: 5000,
      watch: false,
    },
    {
      name: "sentinel-egress", // egress: consome opportunities_queue no RabbitMQ e dispara no WhatsApp
      script: "main.js",
      cwd: path.join(__dirname, "wpp-egress"),
      interpreter: "node",
      autorestart: true,
      max_restarts: 15,
      restart_delay: 5000,
      watch: false,
    },
    {
      name: "sentinel-engine", // engine: consome raw_messages, faz NLP, Neo4j, e despacha no RabbitMQ
      script: "engine.py",
      interpreter: path.join(__dirname, ".venv", ...pythonPath), // monta o caminho dinamicamente dependendo do sistema operacional
      cwd: path.join(__dirname, "intel-engine"),
      env: {
        NODE_ENV: "production"
      },
      autorestart: true,
      max_restarts: 15,
      restart_delay: 5000,
      watch: false,
    },
  ],
};
