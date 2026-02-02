import re
from typing import List, Dict, Any, Tuple
from ingest import data

SELLING_SIGNALS = {
    'strong': [
        ('vendo', 10),
        ('venda', 8),
        ('vendendo', 10),
        ('a venda', 10),
        ('opcao direta', 15),
        ('opcao de parceiro', 15),
        ('oportunidade', 7),
        ('porteira fechada', 12),
        ('entrar e morar', 12),
        ('estuda proposta', 10),
        ('aceita proposta', 10),
        ('lancamento', 8),
        ('aproveite', 7),
    ],
    'medium': [
        ('valor:', 5),
        ('preco:', 5),
        ('condominio:', 4),
        ('iptu:', 4),
        ('taxas:', 4),
        ('vazio:', 6),
        ('reformado', 6),
        ('mobiliado', 6),
        ('exclusivo', 5),
        ('exclusiva', 5),
        ('proprietario', 5),
    ],
    'indicators': [
        ('quartos', 2),
        ('qts', 2),
        ('suites', 2),
        ('suite', 2),
        ('vagas', 2),
        ('vaga', 2),
        ('apartamento', 2),
        ('cobertura', 3),
        ('casa', 2),
        ('duplex', 3),
        ('triplex', 3),
        ('piscina', 2),
        ('varanda', 2),
        ('area de servico', 2),
        ('sala de', 1),
        ('vista', 2),
        ('sol da manha', 2),
        ('de frente', 2),
        ('mobília:', 4),
        ('riserva golf', 2),
        ('opcao', 2),
        ('milhões', 4),
        ('barramares', 4),
    ]
}

BUYING_SIGNALS = {
    'strong': [
        ('preciso', 15),
        ('busco', 15),
        ('busca', 15),
        ('procuro', 15),
        ('compro', 15),
        ('compra', 15),
        ('cliente procura', 20),
        ('cliente busca', 20),
        ('cliente direto', 20),
        ('cliente precisa', 20),
        ('urgente', 10),
        ('ja esta visitando', 15),
        ('alguem tem', 15),
        ('quem tem', 15),
        ('quem teria', 15),
        ('tem opcao', 12),
        ('com opcao', 12),
    ],
    'medium': [
        ('ate', 6),
        ('no maximo', 8),
        ('interesse', 6),
        ('interessado', 6),
        ('frente:', 4),
        ('riserva golf', 2),
        ('opcao', 2),
        ('milhões', 4),
        ('barramares', 4),
    ]
}

USELESS_PATTERNS = [
    r'^(ola|oi|bom dia|boa tarde|boa noite)\s*$',
    r'^https?://[^\s]+\s*$',
    r'^\w+\.(pdf|jpg|jpeg|png|doc|docx)\s*$',
]

def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[*_~`]', '', text)
    
    replacements = {
        'á': 'a', 'à': 'a', 'ã': 'a', 'â': 'a',
        'é': 'e', 'ê': 'e', 'è': 'e',
        'í': 'i', 'ì': 'i', 'î': 'i',
        'ó': 'o', 'õ': 'o', 'ô': 'o', 'ò': 'o',
        'ú': 'u', 'ü': 'u', 'ù': 'u',
        'ç': 'c'
    }
    for old_char, new_char in replacements.items():
        text = text.replace(old_char, new_char)
    
    return text

def calculate_selling_score(normalized_text: str) -> Tuple[int, List[str]]:
    score = 0
    matches = []
    
    for keyword, weight in SELLING_SIGNALS['strong']:
        if keyword in normalized_text:
            score += weight
            matches.append(f"{keyword}(+{weight})")
    
    for keyword, weight in SELLING_SIGNALS['medium']:
        if keyword in normalized_text:
            score += weight
            matches.append(f"{keyword}(+{weight})")
    
    for keyword, weight in SELLING_SIGNALS['indicators']:
        if keyword in normalized_text:
            score += weight
            matches.append(f"{keyword}(+{weight})")
    
    has_price = bool(re.search(r'(r\$|valor:|preco:)\s*[\d.,]+', normalized_text))
    has_area = bool(re.search(r'\d+\s*m[2²]', normalized_text))
    has_rooms = bool(re.search(r'\d+\s*(quarto|suite)', normalized_text))
    has_high_value = bool(re.search(r'[\d.,]+\s*(milhao|milhoes|mil)', normalized_text))
    
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
    
    for keyword, weight in BUYING_SIGNALS['strong']:
        if keyword in normalized_text:
            score += weight
            matches.append(f"{keyword}(+{weight})")
    
    for keyword, weight in BUYING_SIGNALS['medium']:
        if keyword in normalized_text:
            score += weight
            matches.append(f"{keyword}(+{weight})")
    
    return score, matches

def classify_message(message_data: Dict[str, Any], debug: bool = False) -> str:
    message = message_data.get('message', '')
    
    if not message or len(message) < 10:
        return 'useless'
    
    normalized = normalize_text(message)
    
    for pattern in USELESS_PATTERNS:
        if re.match(pattern, normalized.strip()):
            return 'useless'
    
    sell_score, sell_matches = calculate_selling_score(normalized)
    buy_score, buy_matches = calculate_buying_score(normalized)
    
    if debug:
        print(f"\nMensagem: {message[:60]}...")
        print(f"Venda Score: {sell_score} - {sell_matches}")
        print(f"Compra Score: {buy_score} - {buy_matches}")
    
    if 'minhas opcoes' in normalized or 'minhas opcoes diretas' in normalized or 'opcoes diretas para venda' in normalized:
        return 'selling'
    
    if buy_score >= 15:
        if sell_score < buy_score:
            return 'buying'
    
    if sell_score >= 20:
        return 'selling'
    
    if buy_score >= 10 and buy_score > sell_score:
        return 'buying'
    
    if sell_score >= 12 and sell_score > buy_score:
        return 'selling'
    
    return 'useless'

class Message:
    def __init__(self, data_line: Dict[str, Any]):
        self.data = data_line
        self.author_name = data_line.get('author_name', 'Desconhecido')
        self.author_phone = data_line.get('author_phone', 'Desconhecido')
        self.message = data_line.get('message', '')

class SellingMessage(Message): 
    @property
    def stats(self) -> str:
        return (
            f"Corretor: {self.author_name}\n"
            f"Telefone: {self.author_phone}\n"
            f"Anúncio: {self.message}\n"
            "Objetivo: Vender\n\n"
        )

class BuyingMessage(Message):
    @property
    def stats(self) -> str:
        return (
            f"Corretor: {self.author_name}\n"
            f"Telefone: {self.author_phone}\n"
            f"Pedido: {self.message}\n"
            "Objetivo: Comprar\n\n"
        )

class UselessMessage(Message):
    @property
    def stats(self) -> str:
        return (
            f"Corretor: {self.author_name}\n"
            f"Telefone: {self.author_phone}\n"
            f"Conteúdo: {self.message}\n"
            "Objetivo: Unknown\n\n"
        )

def print_statistics(sellers: List[SellingMessage], 
                    buyers: List[BuyingMessage],
                    useless: List[UselessMessage],
                    total: int) -> None:
    print("=" * 80)
    print("RELATÓRIO DE CLASSIFICAÇÃO")
    print("=" * 80)
    print(f"\n📊 ESTATÍSTICAS:")
    print(f"   Total de mensagens: {total}")
    print(f"   Vendas: {len(sellers)} ({len(sellers)/total*100:.1f}%)")
    print(f"   Compras: {len(buyers)} ({len(buyers)/total*100:.1f}%)")
    print(f"   Inúteis: {len(useless)} ({len(useless)/total*100:.1f}%)")
    print("\n" + "=" * 80)

def print_messages(title: str, 
                  messages: List[Message],
                  max_display: int = None) -> None:
    print(f"\n{title}")
    print("=" * 80)
    
    display_count = len(messages) if max_display is None else min(max_display, len(messages))
    
    for message in messages[:display_count]:
        print(message.stats)
    
    if max_display and len(messages) > max_display:
        print(f"... e mais {len(messages) - max_display} mensagens")

def main() -> None: 
    if not data:
        print("Nenhuma mensagem carregada. Encerrando.")
        return
    
    sellers: List[SellingMessage] = []
    buyers: List[BuyingMessage] = []
    useless: List[UselessMessage] = []
    
    for message_data in data:
        classification = classify_message(message_data)
        
        if classification == 'selling':
            sellers.append(SellingMessage(message_data))
        elif classification == 'buying':
            buyers.append(BuyingMessage(message_data))
        else:
            useless.append(UselessMessage(message_data))
    
    # print_statistics(sellers, buyers, useless, len(data))
    # print_messages("🔴 MENSAGENS INÚTEIS:", useless)
    # print_messages("🔵 PEDIDOS DE COMPRA:", buyers)
    print_messages("🟢 ANÚNCIOS DE VENDA:", sellers)

if __name__ == "__main__":
    main()