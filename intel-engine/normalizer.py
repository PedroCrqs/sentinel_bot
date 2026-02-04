from classifier import main
import re
import spacy

nlp = spacy.load("pt_core_news_lg")

sellers, buyers, useless = main()
sellers_padronized = []
buyers_padronized = []

PROPERTY_TYPE_MAP = {
    "APARTAMENTO": ["apartamento", "apto", "ap", "apt", "Apartamento"],
    "CASA": ["casa", "residencia", "residência", "Casa"],
    "TERRENO": ["terreno", "lote"],
    "COBERTURA": ["cobertura", "Cobertura", "cob", "Cob", "COB"]
}

NEIGHBORHOODS = [
    "recreio",
    "barra",
    "jacarepaguá",
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
    ]


class NormalizedAd:
    def __init__(self, raw_text: str, intent: str, original_content):
        self.raw_text = raw_text
        self.intent = intent
        self.text = self._normalize_text(raw_text)
        self.doc = nlp(self.text)
        self.property_type = None
        self.neighborhood = []
        self.price = {"min": None, "max": None}
        self.bedrooms = {"min": None, "max": None}
        self.original_content = original_content

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
            "condominio", "condomínio",
            "iptu", "taxa",
            "foro", "laudemio", "laudêmio"
        ]

        lines = text.splitlines()

        for line in lines:
            if any(word in line for word in forbidden_context):
                continue

            matches = re.findall(r"r\$\s*([\d\.]+,\d{2})", line)
            for m in matches:
                value = m.replace(".", "").replace(",", ".")
                try:
                    prices.append(int(float(value)))
                except ValueError:
                    continue

        if not prices:
            informal = self._parse_money(text)
            if informal:
                prices.extend(informal)

        if not prices:
            self.price = {"min": None, "max": None}
            return self.price

        self.price = {
            "min": min(prices),
            "max": max(prices)
        }
        return self.price

    
    def _parse_money(self, text: str):
        results = []

        patterns = [
            (r"(\d+(?:[\.,]\d+)?)\s*k", 1_000),
            (r"(\d+(?:[\.,]\d+)?)\s*mil", 1_000),
            (r"(\d+(?:[\.,]\d+)?)\s*mi", 1_000_000),
            (r"(\d+(?:[\.,]\d+)?)\s*milh[aã]o", 1_000_000),
            (r"(\d+(?:[\.,]\d+)?)\s*milh[oõ]es", 1_000_000),
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
        numbers = []

        for i, token in enumerate(self.doc):
            if token.like_num and token.text.isdigit():
                window = self.doc[max(0, i-2): i+3]

                for w in window:
                    if w.lemma_ == "quarto":
                        numbers.append(int(token.text))
                        break

        if not numbers:
            self.bedrooms = {"min": None, "max": None}
            return self.bedrooms

        self.bedrooms = {
            "min": min(numbers),
            "max": max(numbers)
        }

        return self.bedrooms

    def extract_neighborhood(self):
        for bairro in NEIGHBORHOODS:
            if bairro in self.text:
                self.neighborhood.append(bairro.upper())

        return self.neighborhood

    def extract_area(self):
        text = self.raw_text.lower()
        areas = []

        patterns = [
            r"(\d{2,4})\s*m²",
            r"(\d{2,4})\s*m2",
            r"(\d{2,4})\s*metros",
            r"(\d{2,4})\s*metros quadrados"
            r"(\d{2,4})\s*m"
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for m in matches:
                try:
                    areas.append(int(m))
                except ValueError:
                    continue

        if not areas:
            self.area_m2 = {"min": None, "max": None}
            return self.area_m2

        self.area_m2 = {
            "min": min(areas),
            "max": max(areas)
        }
        return self.area_m2


   
    def normalize(self):
        self.extract_property_type()
        self.extract_price()
        self.extract_bedrooms()
        self.extract_neighborhood()
        self.extract_area()

        return {
            "intent": self.intent,
            "property_type": self.property_type,
            "neighborhood": self.neighborhood,
            "price": self.price,
            "bedrooms": self.bedrooms,
            "raw_text": self.raw_text,
            "area_m2": self.area_m2,
            # "original_content": self.original_content
    }

for seller in sellers:
    normalized_ad = NormalizedAd(seller.raw_message, 'sell', seller.data)
    sellers_padronized.append(normalized_ad.normalize())

for buyer in buyers:
    normalized_ad = NormalizedAd(buyer.raw_message, 'buy', buyer.data)
    buyers_padronized.append(normalized_ad.normalize())    

print(f'''
        Buyers: {len(buyers_padronized)}
        Sellers: {len(sellers_padronized)}''')
print(sellers_padronized)