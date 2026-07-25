const amqplib = require("amqplib");

const RABBITMQ_URL = process.env.RABBITMQ_URL || "amqp://localhost";
let rabbitChannel = null;

async function initRabbitMQ() {
  try {
    const connection = await amqplib.connect(RABBITMQ_URL);
    rabbitChannel = await connection.createChannel();
    
    // Garante que a fila existe e é persistente
    await rabbitChannel.assertQueue("raw_messages", { durable: true });
    
    console.log("🐰 [RABBITMQ] Conectado! Fila 'raw_messages' pronta.");
  } catch (error) {
    console.error("❌ [RABBITMQ] Erro ao conectar:", error.message);
  }
}

function publishRawMessageEvent(messageId) {
  if (!rabbitChannel) {
    console.warn("⚠️ [RABBITMQ] Canal fechado. Não foi possível publicar o evento.");
    return;
  }
  
  const eventData = JSON.stringify({ message_id: messageId });
  rabbitChannel.sendToQueue("raw_messages", Buffer.from(eventData), {
    persistent: true // Sobrevive a reboots do RabbitMQ
  });
  
  console.log(`🎫 [EVENTO] Mensagem ${messageId} despachada para a fila!`);
}

module.exports = { initRabbitMQ, publishRawMessageEvent };