import re
import spacy

nlp = spacy.load("pt_core_news_lg")

sellers_padronized = []
buyers_padronized = []

PROPERTY_TYPE_MAP = {
    "APARTAMENTO": ["apartamento", "apto", "ap", "apt", "Apartamento"],
    "CASA": ["casa", "residencia", "residência", "Casa"],
    "TERRENO": ["terreno", "lote"],
    "COBERTURA": ["cobertura", "Cobertura", "cob", "Cob", "COB"],
}

NEIGHBORHOODS = [
    "recreio",
    "barra da tijuca",
    "barra olimpica",
    "barra olímpica",
    "barra bonita",
    "barra",
    "jacarepaguá",
    "jacarepagua",
    "vargem grande",
    "vargem pequena",
    "freguesia",
    "ipanema",
    "copacabana",
    "centro da cidade",
    "curicica",
    "taquara",
    "anil",
    "pechincha",
    "itanhangá",
    "itanhanga",
    "humaitá",
    "humaita",
    "pontal oceanico",
]

NEIGHBORHOOD_ALIASES = {
    "barra da tijuca": "BARRA",
    "barra": "BARRA",
    "barra olimpica": "BARRA OLIMPICA",
    "barra olímpica": "BARRA OLIMPICA",
    "jacarepaguá": "JACAREPAGUÁ",
    "jacarepagua": "JACAREPAGUÁ",
    "itanhangá": "ITANHANGÁ",
    "itanhanga": "ITANHANGÁ",
    "humaitá": "HUMAITÁ",
    "humaita": "HUMAITÁ",
}

NEIGHBORHOOD_PARENT = {
    "barra bonita": "RECREIO",
}

CONDOMINIUM = [
    "Acqua Marine",
    "Alameda dos Jequitibás",
    "Alfa Barra",
    "Aloha",
    "Alphaville",
    "Alto Leblon",
    "Americas Park",
    "Art Life",
    "Atlântico Golf",
    "Atlântico Sul",
    "Barra Bali",
    "Barra Central Park",
    "Barramares",
    "Barra Summer Dreams",
    "Barra Sunday",
    "Península",
    "Beauclair",
    "Blue House",
    "Blue Vision",
    "Bora Bora Resort",
    "Bosque da Freguesia",
    "Bosque dos Esquilos",
    "Bothanica Nature",
    "Califórnia Coast",
    "Casa Alta",
    "Duet",
    "Duo Residenziale",
    "Estrelas",
    "Floresta Park",
    "Fontano",
    "Four Seasons",
    "Freedom",
    "Gleba A",
    "Gleba B",
    "Gleba C",
    "Grand Prix",
    "Green Park",
    "Green Place",
    "Icono Parque",
    "Itaúna Gold",
    "Jardim Interlagos",
    "Jardins",
    "Joia da Barra",
    "Le Monde",
    "Le Parc",
    "Liberty Green",
    "Libertá",
    "Life Resort",
    "Liv Lifestyle",
    "Luar do Pontal",
    "Lume Barra Bonita",
    "Lume Residencial",
    "Maayan",
    "Malibu",
    "Mandala",
    "Maramar",
    "Marina Costabella",
    "Mediterrâneo",
    "MORADA DO SOL",
    "MUDRA",
    "Next",
    "Niemeyer",
    "Nova Barra",
    "Nova Ipanema",
    "Nova Sernambetiba",
    "Novo Leblon",
    "Ocean Breeze",
    "Origami",
    "Palais",
    "Palm Springs",
    "Park Premium",
    "Pedra de Itaúna",
    "Península",
    "Planície",
    "Playa",
    "Portal do Parque",
    "Príncipe de Mônaco",
    "Recanto das Garças",
    "Recanto do Pontal",
    "Reserva Jardim",
    "Rio Mar",
    "Riserva Golf",
    "Riviera Del Sol",
    "Royal Green",
    "Santa Marina",
    "Santa Mônica Special",
    "Sublime Max",
    "Sunset",
    "Terra Nossa",
    "Terrazas",
    "Varandas",
    "Verano",
    "Villa Blanca",
    "Villas da Barra",
    "Viverde",
    "Wonderful",
]


class NormalizedAd:
    def __init__(self, raw_text: str, intent: str, original_content):
        self.raw_text = raw_text
        self.intent = intent
        self.text = self._normalize_text(raw_text)
        self.doc = nlp(self.text)
        self.property_type = None
        self.neighborhood = []
        self.price = None
        self.bedrooms = None
        self.area_m2 = None
        self.original_content = original_content
        self.condominium = None
        self.nearbeach = False

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

        for i, line in enumerate(lines):
            if any(word in line for word in forbidden_context):
                continue

            if i > 0:
                prev_line = lines[i - 1]
                if any(word in prev_line for word in forbidden_context):
                    continue

            matches = re.findall(
                r"r\$\s*([\d\.,]+)\s*(milh[oõ]es|milh[aã]o|mil|mi|k)?", line
            )
            for m in matches:
                num_str, suffix = m
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

                    multipliers = {
                        "milhões": 1_000_000,
                        "milhoes": 1_000_000,
                        "milhão": 1_000_000,
                        "milhao": 1_000_000,
                        "mi": 1_000_000,
                        "mil": 1_000,
                        "k": 1_000,
                    }

                    multiplier = multipliers.get(suffix, 1)
                    prices.append(int(base * multiplier))
                except ValueError:
                    continue

        if not prices:
            informal = self._parse_money(text)
            if informal:
                prices.extend(informal)

        if not prices:
            self.price = None
            return self.price

        if self.intent == "sell":
            self.price = min(prices)
        else:
            self.price = max(prices)

        return self.price

    def _parse_money(self, text: str):
        results = []

        patterns = [
            (r"(\d+(?:[\.,]\d+)?)\s*milh[oõ]es", 1_000_000),
            (r"(\d+(?:[\.,]\d+)?)\s*milh[aã]o", 1_000_000),
            (r"(\d+(?:[\.,]\d+)?)\s*mi\b", 1_000_000),
            (r"(\d+(?:[\.,]\d+)?)\s*mil\b", 1_000),
            (r"(\d+(?:[\.,]\d+)?)\s*k\b", 1_000),
        ]

        for pattern, multiplier in patterns:
            matches = re.findall(pattern, text)
            for m in matches:
                try:
                    value = float(m.replace(",", "."))
                    results.append(int(value * multiplier))
                except ValueError:
                    continue

        return results if results else None

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
        replacements = {
            "á": "a",
            "à": "a",
            "ã": "a",
            "â": "a",
            "é": "e",
            "ê": "e",
            "è": "e",
            "í": "i",
            "ì": "i",
            "î": "i",
            "ó": "o",
            "õ": "o",
            "ô": "o",
            "ò": "o",
            "ú": "u",
            "ü": "u",
            "ù": "u",
            "ç": "c",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

    def extract_neighborhood(self):
        text_accented = self.text
        text_no_accent = self._remove_accents(self.text)

        found = set()
        matched_strings = []

        for bairro in sorted(NEIGHBORHOODS, key=len, reverse=True):
            bairro_no_accent = self._remove_accents(bairro)

            in_text = (bairro in text_accented) or (bairro_no_accent in text_no_accent)
            if not in_text:
                continue

            already_covered = any(
                bairro_no_accent in self._remove_accents(longer)
                for longer in matched_strings
            )
            if already_covered:
                continue

            matched_strings.append(bairro)
            canonical = NEIGHBORHOOD_ALIASES.get(bairro, bairro.upper())
            found.add(canonical)

            parent = NEIGHBORHOOD_PARENT.get(bairro)
            if parent:
                found.add(parent)

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
        text_lower = self.raw_text.lower()
        keywords = ["praia", "lúcio costa", "lucio costa"]
        self.nearbeach = any(kw in text_lower for kw in keywords)
        return self.nearbeach

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

    def normalize(self):
        self.extract_property_type()
        self.extract_price()
        self.extract_bedrooms()
        self.extract_neighborhood()
        self.extract_area()
        self.extract_condominium()
        self.extract_nearbeach()

        return {
            "intent": self.intent,
            "property_type": self.property_type,
            "neighborhood": self.neighborhood,
            "price": self.price,
            "bedrooms": self.bedrooms,
            "raw_text": self.raw_text,
            "area_m2": self.area_m2,
            "condominium": self.condominium,
            "nearbeach": self.nearbeach,
            "original_content": self.original_content,
        }


def run_normalizer(sellers, buyers):
    for seller in sellers:
        normalized_ad = NormalizedAd(seller.raw_message, "sell", seller.data)
        sellers_padronized.append(normalized_ad.normalize())

    for buyer in buyers:
        normalized_ad = NormalizedAd(buyer.raw_message, "buy", buyer.data)
        buyers_padronized.append(normalized_ad.normalize())

    return sellers_padronized, buyers_padronized
