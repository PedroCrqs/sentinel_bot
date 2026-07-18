import re
import spacy
from typing import List, Dict, Any, Tuple

# Importando todas as regras e dicionários do arquivo separado!
from classifier_rules import (
    MIN_MESSAGE_LENGTH,
    THRESHOLD_SELL_STRONG,
    THRESHOLD_SELL_WEAK,
    THRESHOLD_BUY_STRONG,
    THRESHOLD_BUY_WEAK,
    SELLING_SIGNALS,
    BUYING_SIGNALS,
    USELESS_PATTERNS,
    RENTAL_KEYWORDS
)

nlp = spacy.load("pt_core_news_lg")

def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[*_~`]", "", text)

    replacements = {
        "á": "a", "à": "a", "ã": "a", "â": "a", "é": "e", "ê": "e", "è": "e",
        "í": "i", "ì": "i", "î": "i", "ó": "o", "õ": "o", "ô": "o", "ò": "o",
        "ú": "u", "ü": "u", "ù": "u", "ç": "c",
    }
    for old_char, new_char in replacements.items():
        text = text.replace(old_char, new_char)

    return text


def calculate_selling_score(normalized_text: str) -> Tuple[int, List[str]]:
    score = 0
    matches = []

    for keyword, weight in SELLING_SIGNALS["strong"]:
        if keyword in normalized_text:
            score += weight
            matches.append(f"{keyword}(+{weight})")

    for keyword, weight in SELLING_SIGNALS["medium"]:
        if keyword in normalized_text:
            score += weight
            matches.append(f"{keyword}(+{weight})")

    for keyword, weight in SELLING_SIGNALS["indicators"]:
        if keyword in normalized_text:
            score += weight
            matches.append(f"{keyword}(+{weight})")

    has_price = bool(re.search(r"(r\$|valor:|preco:)\s*[\d.,]+", normalized_text))
    has_area = bool(re.search(r"\d+\s*m[2²]", normalized_text))
    has_rooms = bool(re.search(r"\d+\s*(quarto|suite)", normalized_text))
    has_high_value = bool(re.search(r"[\d.,]+\s*(milhao|milhoes|mil)", normalized_text))

    if has_price:
        score += 8
        matches.append("preco(+8)")
    if has_area:
        score += 6
        matches.append("area(+6)")
    if has_rooms:
        score += 5
        matches.append("quartos(+5)")
    if has_high_value:
        score += 4
        matches.append("valor_alto(+4)")

    return score, matches


def calculate_buying_score(normalized_text: str) -> Tuple[int, List[str]]:
    score = 0
    matches = []

    for keyword, weight in BUYING_SIGNALS["strong"]:
        if keyword in normalized_text:
            score += weight
            matches.append(f"{keyword}(+{weight})")

    for keyword, weight in BUYING_SIGNALS["medium"]:
        if keyword in normalized_text:
            score += weight
            matches.append(f"{keyword}(+{weight})")

    return score, matches


class Message:
    def __init__(self, data_line: Dict[str, Any]):
        self.data = data_line
        self.author_name = data_line.get("author_name", "Desconhecido")
        self.author_phone = data_line.get("author_phone", "Desconhecido")
        self.raw_message = data_line.get("message", "")
        self.normalized_message = normalize_text(self.raw_message)
        self.doc = nlp(self.normalized_message)
        self.type = ""
        self.sell_score = 0
        self.buy_score = 0

    @property
    def lemmas(self) -> List[str]:
        return [token.lemma_ for token in self.doc if not token.is_stop]

    @property
    def entities(self):
        return [(ent.text, ent.label_) for ent in self.doc.ents]

    def classify(self) -> str:
        if not self.raw_message or len(self.raw_message) < MIN_MESSAGE_LENGTH:
            self.type = "useless"
            return self.type

        if any(kw in self.normalized_message for kw in RENTAL_KEYWORDS):
            self.type = "useless"
            return self.type

        for pattern in USELESS_PATTERNS:
            if re.match(pattern, self.normalized_message.strip()):
                self.type = "useless"
                return self.type

        self.sell_score, _ = calculate_selling_score(self.normalized_message)
        self.buy_score, _ = calculate_buying_score(self.normalized_message)

        if (
            "minhas opcoes" in self.normalized_message
            or "minhas opcoes diretas" in self.normalized_message
            or "opcoes diretas para venda" in self.normalized_message
        ):
            self.type = "selling"
            return self.type

        if self.buy_score >= THRESHOLD_BUY_STRONG:
            if self.sell_score < self.buy_score:
                self.type = "buying"
                return self.type

        if self.sell_score >= THRESHOLD_SELL_STRONG:
            self.type = "selling"
            return self.type

        if self.buy_score >= THRESHOLD_BUY_WEAK and self.buy_score > self.sell_score:
            self.type = "buying"
            return self.type

        if self.sell_score >= THRESHOLD_SELL_WEAK and self.sell_score > self.buy_score:
            self.type = "selling"
            return self.type

        self.type = "useless"
        return self.type

    @property
    def stats(self) -> Dict[str, str]:
        return {
            "corretor": self.author_name,
            "telefone": self.author_phone,
            "conteudo": self.raw_message,
            "objetivo": self.type,
        }


class SellingMessage(Message):
    def __init__(self, data_line: Dict[str, Any]):
        super().__init__(data_line)
        self.type = "selling"


class BuyingMessage(Message):
    def __init__(self, data_line: Dict[str, Any]):
        super().__init__(data_line)
        self.type = "buying"


class UselessMessage(Message):
    def __init__(self, data_line: Dict[str, Any]):
        super().__init__(data_line)
        self.type = "useless"


def print_statistics(
    sellers: List[SellingMessage],
    buyers: List[BuyingMessage],
    useless: List[UselessMessage],
    total: int,
) -> None:
    print("=" * 80)
    print("RELATÓRIO DE CLASSIFICAÇÃO")
    print("=" * 80)
    print(f"\n📊 ESTATÍSTICAS:")
    print(f"   Total de mensagens: {total}")
    print(f"   Vendas: {len(sellers)} ({len(sellers)/total*100:.1f}%)" if total else "   Vendas: 0")
    print(f"   Compras: {len(buyers)} ({len(buyers)/total*100:.1f}%)" if total else "   Compras: 0")
    print(f"   Inúteis: {len(useless)} ({len(useless)/total*100:.1f}%)" if total else "   Inúteis: 0")
    print("\n" + "=" * 80)


def print_messages(
    title: str, messages: List[Message], max_display: int | None = None
) -> None:
    print(f"\n{title}")
    print("=" * 80)

    display_count = (
        len(messages) if max_display is None else min(max_display, len(messages))
    )

    for message in messages[:display_count]:
        stats_dict = message.stats
        print(f"Corretor: {stats_dict['corretor']}")
        print(f"Telefone: {stats_dict['telefone']}")
        print(f"Conteúdo: {stats_dict['conteudo']}")
        print(f"Objetivo: {stats_dict['objetivo']}\n")

    if max_display and len(messages) > max_display:
        print(f"... e mais {len(messages) - max_display} mensagens")


def run_classifier(data) -> tuple:
    if not data:
        print("Nenhuma mensagem carregada. Encerrando.")
        return [], [], []

    sellers: List[SellingMessage] = []
    buyers: List[BuyingMessage] = []
    useless: List[UselessMessage] = []

    for message_data in data:
        base_msg = Message(message_data)
        classification = base_msg.classify()

        if classification == "selling":
            sellers.append(SellingMessage(message_data))
        elif classification == "buying":
            buyers.append(BuyingMessage(message_data))
        else:
            useless.append(UselessMessage(message_data))

    return sellers, buyers, useless