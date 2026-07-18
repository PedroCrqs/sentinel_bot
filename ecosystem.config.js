const path = require("path");

// Configuração pm2 do Sentinel Bot.
// Uso:
//   pm2 start ecosystem.config.js   # inicia os três processos
//   pm2 save                        # persiste a lista atual de processos
//   pm2 startup                     # gera o comando pra iniciar o pm2 no boot do Debian
//
// Ver README.md > "Deploy 24/7 com pm2" para o passo a passo completo.
module.exports = {
  apps: [
    {
      name: "sentinel-collector", // ingest: escuta o grupo, grava data/messages.jsonl
      script: "main.js",
      cwd: path.join(__dirname, "wpp-collector"),
      interpreter: "node",
      autorestart: true,
      max_restarts: 15,
      restart_delay: 5000,
      watch: false,
    },
    {
      name: "sentinel-egress", // egest: lê opportunities/self_opportunities, dispara mensagens
      script: "main.js",
      cwd: path.join(__dirname, "wpp-egress"),
      interpreter: "node",
      autorestart: true,
      max_restarts: 15,
      restart_delay: 5000,
      watch: false,
    },
    {
      name: "sentinel-engine", // classificação, normalização, matching, cleanup periódico
      script: "engine.py",
      interpreter: path.join(__dirname, "intel-engine", "venv", "bin", "python"),
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
