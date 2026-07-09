const fs = require("fs");
const path = require("path");
const qrcode = require("qrcode-terminal");
const { Client, LocalAuth } = require("whatsapp-web.js");

const SESSION_PATH = path.join(__dirname, "session");
const STATE_FILE = path.join(__dirname, "../data/state.json");
const OPPORTUNITIES_FILE = path.join(__dirname, "../data/opportunities.jsonl");
const SELF_OPPORTUNITIES_FILE = path.join(
  __dirname,
  "../data/self_opportunities.jsonl",
);
const GROUP_ID = "120363424642701935@g.us";
// Imóveis próprios: notificação prioritária vai direto por DM, não pro grupo
const PRIORITY_CONTACT_ID = "96654279573661@lid";

if (!fs.existsSync(SESSION_PATH)) {
  fs.mkdirSync(SESSION_PATH, { recursive: true });
}

if (!fs.existsSync(STATE_FILE)) {
  fs.mkdirSync(path.dirname(STATE_FILE), { recursive: true });
  fs.writeFileSync(
    STATE_FILE,
    JSON.stringify({ sent: {}, sent_self: {} }, null, 2),
  );
}

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: SESSION_PATH }),
  puppeteer: {
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  },
});

client.on("qr", (qr) => {
  qrcode.generate(qr, { small: true });
});

client.on("authenticated", () => {
  console.log("=".repeat(80));
  console.log("SENTINEL IN");
  console.log("=".repeat(80));
});

client.once("ready", () => {
  console.log("=".repeat(80));
  console.log("SENTINEL RUNNING");
  console.log("=".repeat(80));
  // TEMP (v1.7.0): dispatch de oportunidades regulares em standby.
  // Só a notificação de imóveis próprios (dispatchSelfLoop) está ativa.
  // Para reativar: descomente a linha abaixo.
  // dispatchLoop();
  dispatchSelfLoop();
});

// client.on("message", async (message) => {
//   const chat = await message.getChat();
//   if (chat.isGroup) {
//     console.log(`Grupo: ${chat.name}`);
//     console.log(`ID: ${chat.id._serialized}`);
//     console.log("=".repeat(80));
//   }
// });

client.on("disconnected", (reason) => {
  console.log("=".repeat(80));
  console.warn("DISCONECTED:", reason);
  console.log("=".repeat(80));
});

client.on("auth_failure", (msg) => {
  console.log("=".repeat(80));
  console.error("AUTH FAILURE:", msg);
  console.log("=".repeat(80));
});

async function dispatchOpportunities({
  filepath,
  stateKey,
  destination,
  prefix,
}) {
  try {
    if (!fs.existsSync(filepath)) return;

    const state = JSON.parse(fs.readFileSync(STATE_FILE));
    if (!state[stateKey]) state[stateKey] = {};

    const lines = fs.readFileSync(filepath, "utf8").split("\n");

    for (const line of lines) {
      if (!line.trim()) continue;

      const opp = JSON.parse(line);

      if (state[stateKey][opp.id]) continue;

      const msg = prefix ? `${prefix}\n\n${format(opp)}` : format(opp);

      await client.sendMessage(destination, msg);
      console.log(`Sent (${stateKey}): ${opp.id}`);

      state[stateKey][opp.id] = true;
      fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));

      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
  } catch (error) {
    console.error(`Dispatch error (${stateKey}):`, error.message);
  }
}

async function dispatchLoop() {
  await dispatchOpportunities({
    filepath: OPPORTUNITIES_FILE,
    stateKey: "sent",
    destination: GROUP_ID,
  });
  setTimeout(dispatchLoop, 5000);
}

async function dispatchSelfLoop() {
  await dispatchOpportunities({
    filepath: SELF_OPPORTUNITIES_FILE,
    stateKey: "sent_self",
    destination: PRIORITY_CONTACT_ID,
    prefix: "⭐ *IMÓVEL PRÓPRIO*",
  });
  setTimeout(dispatchSelfLoop, 5000);
}

function format(o) {
  const buyer = o.buyer.original_content;
  const seller = o.seller.original_content;

  const formatPrice = (price) => {
    if (!price) return "Não informado";
    return `R$ ${price.toLocaleString("pt-BR")}`;
  };

  const formatArea = (area) => {
    if (!area) return "";
    return `${area}m²`;
  };

  const formatBedrooms = (bedrooms) => {
    if (!bedrooms) return "";
    return `${bedrooms} quarto${bedrooms > 1 ? "s" : ""}`;
  };

  const formatNeighborhood = (neighborhoods, subNeighborhood) => {
    if (!neighborhoods || neighborhoods.length === 0) return "Não informado";
    if (subNeighborhood) {
      const parent = neighborhoods.find((n) => n !== subNeighborhood);
      return parent ? `${parent} › ${subNeighborhood}` : subNeighborhood;
    }
    return neighborhoods.join(", ");
  };

  const formatCondominium = (condominium) => {
    if (!condominium) return null;
    if (Array.isArray(condominium)) {
      return condominium.length > 0 ? condominium.join(", ") : null;
    }
    return condominium;
  };

  let message = `🔥 *OPORTUNIDADE* | Score: ${o.score}\n`;
  message += `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n`;

  message += `👤 *COMPRADOR*\n`;
  message += `Corretor: ${buyer.author_name}\n`;
  message += `Telefone: ${buyer.author_phone || "Não informado"}\n`;
  message += `📍 ${formatNeighborhood(o.buyer.neighborhood, o.buyer.sub_neighborhood)}\n`;
  message += `💰 Até ${formatPrice(o.buyer.price)}\n`;

  const buyerDetails = [];
  if (o.buyer.bedrooms) buyerDetails.push(formatBedrooms(o.buyer.bedrooms));
  if (o.buyer.area_m2) buyerDetails.push(formatArea(o.buyer.area_m2));
  if (o.buyer.property_type) buyerDetails.push(o.buyer.property_type);
  if (buyerDetails.length > 0) {
    message += `🏠 ${buyerDetails.join(" • ")}\n`;
  }

  const buyerCond = formatCondominium(o.buyer.condominium);
  if (buyerCond) message += `🏘️ Cond: ${buyerCond}\n`;
  if (o.buyer.nearbeach) message += `🌊 Próximo à praia\n`;
  if (o.buyer.seafront) message += `🏖️ Frente mar\n`;
  if (o.buyer.sun_type)
    message += `☀️ Sol: ${o.buyer.sun_type.charAt(0) + o.buyer.sun_type.slice(1).toLowerCase()}\n`;
  if (o.buyer.parking_spots)
    message += `🚗 ${o.buyer.parking_spots} vaga${o.buyer.parking_spots > 1 ? "s" : ""}\n`;
  if (o.buyer.zone) message += `🗺️ Zona: ${o.buyer.zone}\n`;

  message += `\nTexto original:\n_${o.buyer.raw_text}_\n`;

  message += `\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n`;

  message += `🏢 *VENDEDOR*\n`;
  message += `Corretor: ${seller.author_name}\n`;
  message += `Telefone: ${seller.author_phone || "Não informado"}\n`;
  message += `📍 ${formatNeighborhood(o.seller.neighborhood, o.seller.sub_neighborhood)}\n`;
  message += `💰 ${formatPrice(o.seller.price)}\n`;

  const sellerDetails = [];
  if (o.seller.bedrooms) sellerDetails.push(formatBedrooms(o.seller.bedrooms));
  if (o.seller.area_m2) sellerDetails.push(formatArea(o.seller.area_m2));
  if (o.seller.property_type) sellerDetails.push(o.seller.property_type);
  if (sellerDetails.length > 0) {
    message += `🏠 ${sellerDetails.join(" • ")}\n`;
  }

  const sellerCond = formatCondominium(o.seller.condominium);
  if (sellerCond) message += `🏘️ Cond: ${sellerCond}\n`;
  if (o.seller.nearbeach) message += `🌊 Próximo à praia\n`;
  if (o.seller.seafront) message += `🏖️ Frente mar\n`;
  if (o.seller.sun_type)
    message += `☀️ Sol: ${o.seller.sun_type.charAt(0) + o.seller.sun_type.slice(1).toLowerCase()}\n`;
  if (o.seller.parking_spots)
    message += `🚗 ${o.seller.parking_spots} vaga${o.seller.parking_spots > 1 ? "s" : ""}\n`;

  message += `\nTexto original:\n_${o.seller.raw_text}_`;

  return message;
}

client.initialize();
