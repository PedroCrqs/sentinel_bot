import re
from typing import List, Dict, Any
from ingest import data

SELLER_KEYWORDS = [
    'vendo', 'venda', 'a venda', 'r$', 'valor:', 'preco:','localizado', 'fica no', 'fica na', 'localizacao:', 'oportunidade', 'lancamento', 'exclusivo', 'exclusiva','suite', 'suites', 'quartos', 'vagas', 'garagem','condominio:', 'iptu:', 'iptu', 'area de', 'm²', 'm2', 'cobertura', 'apartamento', 'casa', 'triplex', 'duplex', 'infraestrutura', 'porteira fechada', 'mobiliado', 'reformado', 'piscina', 'varanda', 'lavabo', 'area gourmet','estuda proposta', 'aceita proposta', 'aceita financiamento','entrar e morar','barra', 'recreio', 'leblon', 'ipanema', 'botafogo',
    'jardim oceanico', 'av.', 'avenida', 'rua', 'estrada'
]

BUYER_KEYWORDS = [
    'compro', 'busco', 'procuro', 'preciso', 'procura',
    'cliente', 'cliente procura', 'cliente busca',
    'urgente', 'ja esta visitando','interesse', 'interessado'
]

USEFUL_INDICATORS = [
    'condominio:', 'iptu:', 'valor:', 'r$', 'preco:',
    'suite', 'quarto', 'vaga', 'm²', 'm2'
]

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
            f"Anúncio: {self.message}\n\n"
        )

class BuyingMessage(Message):
    @property
    def stats(self) -> str:
        return (
            f"Corretor: {self.author_name}\n"
            f"Telefone: {self.author_phone}\n"
            f"Pedido: {self.message}\n\n"
        )

class UselessMessage(Message):
    @property
    def stats(self) -> str:
        return (
            f"Corretor: {self.author_name}\n"
            f"Telefone: {self.author_phone}\n"
            f"Conteúdo: {self.message}\n\n"
        )

def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[*_~`]', '', text)
    
    replacements = {
        'á': 'a', 'à': 'a', 'ã': 'a', 'â': 'a',
        'é': 'e', 'ê': 'e',
        'í': 'i',
        'ó': 'o', 'õ': 'o', 'ô': 'o',
        'ú': 'u', 'ü': 'u',
        'ç': 'c'
    }
    for old_char, new_char in replacements.items():
        text = text.replace(old_char, new_char)
    
    return text


def classify_message(message_data: Dict[str, Any]) -> str:
    message = message_data.get('message', '')
    if not message:
        return 'useless'
    
    normalized_message = normalize_text(message)
    
    buyer_score = sum(
        1 for keyword in BUYER_KEYWORDS 
        if keyword in normalized_message
    )
    
    seller_score = sum(
        1 for keyword in SELLER_KEYWORDS 
        if keyword in normalized_message
    )
    
    if buyer_score > 0:
        return 'buying'
    if seller_score >= 2:
        return 'selling'
    if any(indicator in normalized_message for indicator in USEFUL_INDICATORS):
        return 'selling'
    
    return 'useless'


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
    
    print_statistics(sellers, buyers, useless, len(data))
    print_messages("🔴 MENSAGENS INÚTEIS:", useless)
    print_messages("🔵 PEDIDOS DE COMPRA:", buyers)
    print_messages("🟢 ANÚNCIOS DE VENDA :", sellers)

if __name__ == "__main__":
    main()