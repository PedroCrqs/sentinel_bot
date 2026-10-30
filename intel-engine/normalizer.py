import re
import spacy
import json
import os
import unicodedata

nlp = spacy.load("pt_core_news_lg")

# sellers_padronized = []
# buyers_padronized = []

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "data", "entities.json")

# Carrega os dados do arquivo JSON
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

PROPERTY_TYPE_MAP = config["PROPERTY_TYPE_MAP"]
NEIGHBORHOODS = config["NEIGHBORHOODS"]
NEIGHBORHOOD_ALIASES = config["NEIGHBORHOOD_ALIASES"]
NEIGHBORHOOD_PARENT = config["NEIGHBORHOOD_PARENT"]
ZONES = config["ZONES"]
CONDOMINIUM = config["CONDOMINIUM"]

SUB_NEIGHBORHOODS = list(NEIGHBORHOOD_PARENT.keys())


def remove_accents_str(text: str) -> str:
    """Remove acentos de uma string para comparações case/accent-insensitive."""
    if not text:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )

def extract_phone_from_text(text: str) -> str | None:
    if not text:
        return None
    m_wame = re.search(r"wa\.me/(?:55)?([1-9]{2}9?\d{8})", text, re.I)
    if m_wame:
        d = m_wame.group(1)
        return f"55{d}" if len(d) == 11 else d
    m_cell = re.search(r"(?:\+?55\s?)?(?:\(?([1-9]{2})\)?\s?)?(?:9\s?\d{4})[-\s]?(\d{4})\b", text)
    if m_cell:
        digits = re.sub(r"\D", "", m_cell.group(0))
        if len(digits) == 9:
            return f"5521{digits}"
        elif len(digits) == 11:
            return f"55{digits}"
        elif len(digits) == 13:
            return digits
    m_land = re.search(r"(?:\+?55\s?)?(?:\(?([1-9]{2})\)?\s?)?(?:[2-5]\d{3})[-\s]?(\d{4})\b", text)
    if m_land:
        digits = re.sub(r"\D", "", m_land.group(0))
        if len(digits) == 8:
            return f"5521{digits}"
        elif len(digits) == 10:
            return f"55{digits}"
        elif len(digits) == 12:
            return digits
    return None
def is_lid(phone_val) -> bool:
    """Verifica se o valor de telefone é nulo, inválido ou um identificador LID do WhatsApp."""
    if not phone_val:
        return True
    s = str(phone_val).strip()
    if "@lid" in s or s.lower() in {"desconhecido", "none", "null", ""}:
        return True
    digits = re.sub(r"\D", "", s)
    if len(digits) > 13 or len(digits) < 10:
        return True
    return False



def canonical_neighborhood(raw_name: str) -> str:
    """Retorna o nome canônico do bairro para o grafo Neo4j.
    
    Garante que nomes originados do banco relacional (ex: 'Barra da Tijuca',
    'Recreio dos Bandeirantes', 'Barra Olímpica') sejam mapeados para a mesma
    identidade canônica usada pelo normalizer NLP e pelas demandas dos clientes
    ('BARRA', 'RECREIO', 'BARRA OLIMPICA').
    """
    if not raw_name:
        return "DESCONHECIDO"
    name = raw_name.strip().lower()

    # 1. Alias exato
    if name in NEIGHBORHOOD_ALIASES:
        return NEIGHBORHOOD_ALIASES[name]

    # 2. Alias sem acentos
    name_no_acc = remove_accents_str(name)
    for alias_key, alias_val in NEIGHBORHOOD_ALIASES.items():
        if remove_accents_str(alias_key) == name_no_acc:
            return alias_val

    # 3. Sub-bairro / parent
    if name in NEIGHBORHOOD_PARENT:
        return NEIGHBORHOOD_PARENT[name]
    for parent_key, parent_val in NEIGHBORHOOD_PARENT.items():
        if remove_accents_str(parent_key) == name_no_acc:
            return parent_val

    # 4. Busca em bairros conhecidos (longest first)
    for nb in sorted(NEIGHBORHOODS, key=len, reverse=True):
        nb_no_acc = remove_accents_str(nb)
        if nb in name or nb_no_acc in name_no_acc:
            return NEIGHBORHOOD_ALIASES.get(nb, nb.upper())

    return raw_name.strip().upper()


def normalize_sun_type(value) -> str | None:
    """Normaliza o tipo de sol para os valores canônicos do matcher: 'MANHA', 'TARDE', 'PASSANTE'."""
    if not value:
        return None
    val_clean = remove_accents_str(str(value).strip().upper())
    if "MANHA" in val_clean:
        return "MANHA"
    if "TARDE" in val_clean:
        return "TARDE"
    if "PASSANTE" in val_clean:
        return "PASSANTE"
    return val_clean


class NormalizedAd:
    def __init__(self, raw_text: str, intent: str, original_content: dict | None = None):
        self.raw_text = raw_text
        self.intent = intent
        self.text = self._normalize_text(raw_text)
        self.doc = nlp(self.text)
        self.property_type = None
        self.neighborhood = []
        self.price = None
        self.bedrooms = None
        self.area_m2 = None
        self.original_content = original_content or None
        self.condominium = None
        self.nearbeach = False
        self.seafront = False
        self.sun_type = None
        self.parking_spots = None
        self.zone = None
        self.sub_neighborhood = None

        # Enriquece telefone do autor caso seja um LID ou esteja vazio
        if self.original_content:
            curr_phone = self.original_content.get("author_phone")
            if is_lid(curr_phone):
                extracted_p = extract_phone_from_text(raw_text)
                if extracted_p:
                    self.original_content["author_phone"] = extracted_p

    def _normalize_text(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def extract_property_type(self):
        for token in self.doc:
            lemma = token.lemma_

            for prop_type, keywords in PROPERTY_TYPE_MAP.items():
                if lemma in keywords:
                    self.property_type = prop_type
                    return self.property_type

        return None

    def extract_price(self):
        prices = []
        text = self.raw_text.lower()

        forbidden_context = [
            "condominio",
            "condomínio",
            "cond",
            "iptu",
            "taxa",
            "foro",
            "laudemio",
            "laudêmio",
        ]

        lines = text.splitlines()

        multipliers = {
            "milhões": 1_000_000,
            "milhoes": 1_000_000,
            "milhão": 1_000_000,
            "milhao": 1_000_000,
            "mi": 1_000_000,
            "m": 1_000_000,
            "mil": 1_000,
            "k": 1_000,
        }

        for i, line in enumerate(lines):
            if any(word in line for word in forbidden_context):
                continue

            if i > 0:
                prev_line = lines[i - 1]
                if any(word in prev_line for word in forbidden_context):
                    continue

            patterns = [
                # Precedido por R$ ou palavras-chave (valor, ate, por, teto, etc)
                r"(?:r\$\s*|valor:?\s*|preco:?\s*|preço:?\s*|at[eé]:?\s*|por\s+|teto:?\s*|or[cç]amento:?\s*|m[aá]ximo:?\s*)([\d\.,]+)\s*(milh[oõ]es|milh[aã]o|mil|mi|m|k)?\b",
                # Sufixos explícitos independentes: 800k, 800 mil, 1.8mi, 1.8m
                r"\b([\d\.,]+)\s*(milh[oõ]es|milh[aã]o|mil|mi|m|k)\b",
                # Notação monetária tradicional
                r"r\$\s*([\d\.,]+)\b",
                # Valores numéricos no formato de milhares (ex: 800.000)
                r"\b(\d{1,3}(?:\.\d{3})+(?:,\d{2})?)\b",
            ]

            for pat in patterns:
                for m in re.finditer(pat, line, re.I):
                    groups = m.groups()
                    num_str = groups[0]
                    suffix = (groups[1].lower() if len(groups) > 1 and groups[1] else "").strip()
                    try:
                        if "," in num_str and "." in num_str:
                            value = num_str.replace(".", "").replace(",", ".")
                        elif "," in num_str:
                            value = num_str.replace(",", ".")
                        elif num_str.count(".") > 1:
                            value = num_str.replace(".", "")
                        elif "." in num_str and suffix:
                            value = num_str
                        elif "." in num_str and not suffix:
                            value = num_str.replace(".", "")
                        else:
                            value = num_str

                        base = float(value)
                        multiplier = multipliers.get(suffix, 1)
                        val = int(base * multiplier)

                        # Valores de imóveis devem ser de pelo menos 50 mil reais
                        if val >= 50_000:
                            prices.append(val)
                    except ValueError:
                        continue

        if not prices:
            self.price = None
            return self.price

        self.price = max(prices)
        return self.price

    def extract_area(self):
        text = self.raw_text.lower()
        areas = []

        patterns = [
            r"(\d{2,4})\s*m²",
            r"(\d{2,4})\s*m2",
            r"(\d{2,4})\s*metros\s*quadrados",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for m in matches:
                try:
                    areas.append(int(m))
                except ValueError:
                    continue

        if not areas:
            self.area_m2 = None
            return self.area_m2

        if self.intent == "sell":
            self.area_m2 = max(areas)
        else:
            self.area_m2 = min(areas)

        return self.area_m2

    def extract_parking_spots(self):
        text = self.raw_text.lower()
        spots = []

        patterns = [
            r"(\d+)\s*vaga[s]?\b",
            r"vaga[s]?\s*:?\s*(\d+)",
            r"(\d+)\s*garagem\b",
            r"garagem\s*:?\s*(\d+)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for m in matches:
                try:
                    spots.append(int(m))
                except ValueError:
                    continue

        if not spots:
            self.parking_spots = None
            return self.parking_spots

        if self.intent == "sell":
            self.parking_spots = max(spots)
        else:
            self.parking_spots = min(spots)

        return self.parking_spots

    def extract_bedrooms(self):
        text = self.raw_text.lower()
        bedrooms = []

        direct_patterns = [
            r"quartos?\s*:?\s*(\d+)",
            r"(\d+)\s*quartos?",
            r"qts?\s*:?\s*(\d+)",
            r"(\d+)\s*qts?",
        ]

        for pattern in direct_patterns:
            matches = re.findall(pattern, text)
            for m in matches:
                try:
                    bedrooms.append(int(m))
                except ValueError:
                    continue

        if not bedrooms:
            suite_patterns = [
                r"suites?\s*:?\s*(\d+)",
                r"(\d+)\s*suites?",
                r"suítes?\s*:?\s*(\d+)",
                r"(\d+)\s*suítes?",
            ]

            for pattern in suite_patterns:
                matches = re.findall(pattern, text)
                for m in matches:
                    try:
                        bedrooms.append(int(m))
                    except ValueError:
                        continue

        if not bedrooms:
            text_nums = {
                "um": 1,
                "uma": 1,
                "dois": 2,
                "duas": 2,
                "tres": 3,
                "três": 3,
                "quatro": 4,
                "cinco": 5,
            }

            bedroom_terms = {"quarto", "quartos", "qt", "qts"}
            suite_terms = {"suite", "suites", "suíte", "suítes"}

            for i, token in enumerate(self.doc):
                value = None

                if token.like_num:
                    clean = re.sub(r"[^\d]", "", token.text)
                    if clean:
                        value = int(clean)
                else:
                    value = text_nums.get(token.lemma_.lower())

                if value is None or value > 20:
                    continue

                window = self.doc[max(0, i - 3) : i + 4]

                for w in window:
                    lemma = w.lemma_.lower()

                    if lemma in bedroom_terms or lemma in suite_terms:
                        bedrooms.append(value)
                        break

        if not bedrooms:
            self.bedrooms = None
            return self.bedrooms

        self.bedrooms = max(bedrooms)
        return self.bedrooms

    def _remove_accents(self, text: str) -> str:
        return remove_accents_str(text)

    def extract_neighborhood(self):
        text_accented = self.text
        text_no_accent = self._remove_accents(self.text)

        found = set()
        matched_strings = []

        # 1. Primeiro verifica sub-bairros e condomínios com mapeamento de bairro pai (NEIGHBORHOOD_PARENT)
        for place, parent in sorted(NEIGHBORHOOD_PARENT.items(), key=lambda x: len(x[0]), reverse=True):
            place_no_acc = self._remove_accents(place.lower())
            pattern = r"\b" + re.escape(place_no_acc) + r"\b"
            if re.search(pattern, text_no_accent):
                canonical = NEIGHBORHOOD_ALIASES.get(place, place.upper())
                found.add(canonical)
                if isinstance(parent, list):
                    for p in parent:
                        found.add(p)
                else:
                    found.add(parent)

                # Vinculação dual histórica de Maayan / Cidade Jardim em Barra Olímpica e Barra da Tijuca
                if place_no_acc in {"maayan", "cidade jardim"}:
                    found.add("BARRA")
                    found.add("BARRA OLIMPICA")

                self.sub_neighborhood = canonical
                matched_strings.append(place)
                # Mascara este termo para que substrings não acionem bairros gerais incorretos (ex: Barra em Barra Sunday)
                text_no_accent = re.sub(pattern, " " * len(place_no_acc), text_no_accent)
                text_accented = re.sub(r"\b" + re.escape(place.lower()) + r"\b", " " * len(place), text_accented)

        # 2. Mascara outros condomínios conhecidos para evitar falsos positivos nos bairros
        for cond in sorted(CONDOMINIUM, key=len, reverse=True):
            cond_accented = cond.lower()
            cond_no_accent = self._remove_accents(cond_accented)
            pattern_no_acc = r"\b" + re.escape(cond_no_accent) + r"\b"
            if re.search(pattern_no_acc, text_no_accent):
                canonical = cond.upper()
                found.add(canonical)
                text_no_accent = re.sub(pattern_no_acc, " " * len(cond_no_accent), text_no_accent)
                text_accented = re.sub(r"\b" + re.escape(cond_accented) + r"\b", " " * len(cond), text_accented)

        # 3. Mapeia bairros conhecidos no restante do texto
        for bairro in sorted(NEIGHBORHOODS, key=len, reverse=True):
            bairro_no_accent = self._remove_accents(bairro)
            pattern = r"\b" + re.escape(bairro_no_accent) + r"\b"

            if re.search(pattern, text_no_accent):
                canonical = NEIGHBORHOOD_ALIASES.get(bairro, bairro.upper())
                found.add(canonical)
                matched_strings.append(bairro)
                text_no_accent = re.sub(pattern, " " * len(bairro_no_accent), text_no_accent)

        self.neighborhood = list(found)
        return self.neighborhood

    def extract_condominium(self):
        text_lower = self.raw_text.lower()
        if self.intent == "buy":
            found = []
            for cond in sorted(CONDOMINIUM, key=len, reverse=True):
                if cond.lower() in text_lower:
                    found.append(cond)
            self.condominium = found if found else None
        else:
            for cond in sorted(CONDOMINIUM, key=len, reverse=True):
                if cond.lower() in text_lower:
                    self.condominium = cond
                    return self.condominium
        return self.condominium

    def extract_nearbeach(self):
        text_lower = self._remove_accents(self.raw_text.lower())
        keywords = ["praia", "lucio costa"]
        self.nearbeach = any(kw in text_lower for kw in keywords)

        seafront_keywords = ["frente mar", "frontal mar", "pe na areia"]
        self.seafront = any(kw in text_lower for kw in seafront_keywords)

        if self.seafront:
            self.nearbeach = True

        return self.nearbeach

    def extract_sun_type(self):
        text_lower = self._remove_accents(self.raw_text.lower())

        morning_keywords = ["sol da manha", "sol manha"]
        afternoon_keywords = ["sol da tarde", "sol tarde"]
        passthrough_keywords = ["sol passante", "passante"]

        if any(kw in text_lower for kw in morning_keywords):
            self.sun_type = "MANHA"
        elif any(kw in text_lower for kw in afternoon_keywords):
            self.sun_type = "TARDE"
        elif any(kw in text_lower for kw in passthrough_keywords):
            self.sun_type = "PASSANTE"
        else:
            self.sun_type = None

        return self.sun_type

    def extract_zone(self):
        text_no_accent = self._remove_accents(self.raw_text.lower())

        if self.intent == "buy":
            for zone_name, zone_data in ZONES.items():
                for alias in sorted(zone_data["aliases"], key=len, reverse=True):
                    pattern = r"\b" + re.escape(self._remove_accents(alias)) + r"\b"
                    if re.search(pattern, text_no_accent):
                        self.zone = zone_name
                        existing = set(self.neighborhood)
                        for n in zone_data["neighborhoods"]:
                            existing.add(n)
                        self.neighborhood = list(existing)
                        return self.zone
        else:
            for neighborhood in self.neighborhood:
                for zone_name, zone_data in ZONES.items():
                    if neighborhood.upper() in zone_data["neighborhoods"]:
                        self.zone = zone_name
                        return self.zone

        self.zone = None
        return None

    def normalize(self):
        self.extract_property_type()
        self.extract_price()
        self.extract_bedrooms()
        self.extract_neighborhood()
        self.extract_zone()
        self.extract_area()
        self.extract_parking_spots()
        self.extract_condominium()
        self.extract_nearbeach()
        self.extract_sun_type()

        if self.intent == "sell" and len(self.neighborhood) > 1:
            if self.sub_neighborhood and self.sub_neighborhood in self.neighborhood:
                self.neighborhood = [self.sub_neighborhood]
            else:
                self.neighborhood = [max(self.neighborhood, key=len)]

        return {
            "intent": self.intent,
            "property_type": self.property_type,
            "neighborhood": self.neighborhood,
            "sub_neighborhood": self.sub_neighborhood,
            "zone": self.zone,
            "price": self.price,
            "bedrooms": self.bedrooms,
            "raw_text": self.raw_text,
            "area_m2": self.area_m2,
            "parking_spots": self.parking_spots,
            "condominium": self.condominium,
            "nearbeach": self.nearbeach,
            "seafront": self.seafront,
            "sun_type": self.sun_type,
            "original_content": self.original_content,
        }


def run_normalizer(sellers, buyers):
    sellers_padronized = []
    buyers_padronized = []

    for seller in sellers:
        normalized_ad = NormalizedAd(seller.raw_message, "sell", seller.data)
        sellers_padronized.append(normalized_ad.normalize())

    for buyer in buyers:
        normalized_ad = NormalizedAd(buyer.raw_message, "buy", buyer.data)
        buyers_padronized.append(normalized_ad.normalize())

    return sellers_padronized, buyers_padronized


def run_self_normalizer(self_ads: list[dict]) -> list:
    normalized_ads = []
    for ad in self_ads:
        normalized_ad = NormalizedAd(ad["message"], "sell", ad)
        normalized_ads.append(normalized_ad.normalize())
    return normalized_ads
