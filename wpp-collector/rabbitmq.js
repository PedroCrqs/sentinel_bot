const amqplib = require("amqplib");

const RABBITMQ_URL = process.env.RABBITMQ_URL || "amqp://localhost:5672";
const RECONNECT_BASE_MS = 5000;
const RECONNECT_MAX_MS = 30000;

let rabbitConnection = null;
let rabbitChannel = null;
let isConnecting = false;
let reconnectTimer = null;
let reconnectAttempts = 0;

function scheduleReconnect() {
  if (reconnectTimer || isConnecting) return;

  const delayMs = Math.min(
    RECONNECT_BASE_MS * Math.pow(2, reconnectAttempts),
    RECONNECT_MAX_MS
  );
  reconnectAttempts += 1;

  console.warn(
    `🔄 [RABBITMQ] Agendando reconexão em ${Math.round(delayMs / 1000)}s...`
  );
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    initRabbitMQ();
  }, delayMs);
}

async function initRabbitMQ() {
  if (isConnecting || rabbitChannel) return;
  isConnecting = true;

  try {
    const connection = await amqplib.connect(RABBITMQ_URL);
    rabbitConnection = connection;

    connection.on("close", (err) => {
      console.error(
        "❌ [RABBITMQ] Conexão fechada:",
        err ? err.message : "sem detalhes"
      );
      rabbitConnection = null;
      rabbitChannel = null;
      scheduleReconnect();
    });

    connection.on("error", (err) => {
      console.error("❌ [RABBITMQ] Erro na conexão:", err.message);
    });

    const channel = await connection.createChannel();
    channel.on("close", () => {
      console.warn("⚠️ [RABBITMQ] Canal fechado.");
      rabbitChannel = null;
      if (rabbitConnection) {
        scheduleReconnect();
      }
    });

    channel.on("error", (err) => {
      console.error("❌ [RABBITMQ] Erro no canal:", err.message);
    });

    // Garante que a fila existe e é persistente
    await channel.assertQueue("raw_messages", { durable: true });

    rabbitChannel = channel;
    reconnectAttempts = 0;
    console.log("🐰 [RABBITMQ] Conectado! Fila 'raw_messages' pronta.");
  } catch (error) {
    console.error("❌ [RABBITMQ] Erro ao conectar:", error.message);
    rabbitConnection = null;
    rabbitChannel = null;
    scheduleReconnect();
  } finally {
    isConnecting = false;
  }
}

function publishRawMessageEvent(messageId) {
  if (!rabbitChannel) {
    console.warn(
      "⚠️ [RABBITMQ] Canal fechado. Não foi possível publicar o evento."
    );
    scheduleReconnect();
    return false;
  }

  try {
    const eventData = JSON.stringify({ message_id: messageId });
    rabbitChannel.sendToQueue("raw_messages", Buffer.from(eventData), {
      persistent: true, // Sobrevive a reboots do RabbitMQ
    });

    console.log(`🎫 [EVENTO] Mensagem ${messageId} despachada para a fila!`);
    return true;
  } catch (error) {
    console.error("❌ [RABBITMQ] Falha ao publicar evento:", error.message);
    rabbitChannel = null;
    scheduleReconnect();
    return false;
  }
}

module.exports = { initRabbitMQ, publishRawMessageEvent };
