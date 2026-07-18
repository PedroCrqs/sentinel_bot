# dicionários de sinais de compra e venda, usados para classificar mensagens como "compra" ou "venda"

# ==============================================================================
# CONFIGURAÇÕES DE CLASSIFICAÇÃO (Limites e Pesos)
# ==============================================================================
MIN_MESSAGE_LENGTH = 10
THRESHOLD_SELL_STRONG = 20
THRESHOLD_SELL_WEAK = 12
THRESHOLD_BUY_STRONG = 15
THRESHOLD_BUY_WEAK = 10

# ==============================================================================
# DICIONÁRIOS DE SINAIS
# ==============================================================================
SELLING_SIGNALS = {
    "strong": [
        ("vendo", 10), ("venda", 8), ("vendendo", 10), ("a venda", 10),
        ("opcao direta", 15), ("opcao de parceiro", 15), ("oportunidade", 7),
        ("porteira fechada", 12), ("entrar e morar", 12), ("estuda proposta", 10),
        ("aceita proposta", 10), ("lancamento", 8), ("aproveite", 7),
    ],
    "medium": [
        ("valor:", 5), ("preco:", 5), ("condominio:", 4), ("iptu:", 4),
        ("taxas:", 4), ("vazio:", 6), ("reformado", 6), ("mobiliado", 6),
        ("exclusivo", 5), ("exclusiva", 5), ("proprietario", 5), ("entrega imediata", 5),
    ],
    "indicators": [
        ("quartos", 2), ("qts", 2), ("suites", 2), ("suite", 2),
        ("vagas", 2), ("vaga", 2), ("apartamento", 2), ("cobertura", 3),
        ("casa", 2), ("duplex", 3), ("triplex", 3), ("piscina", 2),
        ("varanda", 2), ("area de servico", 2), ("sala de", 1),
        ("vista", 2), ("sol da manha", 2), ("de frente", 2),
        ("mobília:", 4), ("riserva golf", 2), ("opcao", 2),
        ("milhões", 4), ("barramares", 4),
    ],
}

BUYING_SIGNALS = {
    "strong": [
        ("preciso", 15), ("busco", 15), ("busca", 15), ("buscando", 15),
        ("procuro", 15), ("procurando", 15), ("procura", 15), ("compro", 15),
        ("compra", 15), ("cliente procura", 20), ("cliente busca", 20),
        ("cliente direto", 20), ("cliente precisa", 20), ("cliente interessada", 20),
        ("cliente interessado", 20), ("cliente querendo", 20), ("urgente", 10),
        ("ja esta visitando", 15), ("alguém tem", 15), ("alguém vende", 15),
        ("quem tem", 15), ("quem tiver", 15), ("estuda proposta", 15),
        ("quem teria", 15), ("tem opcao", 12), ("com opcao", 12),
    ],
    "medium": [
        ("ate", 6), ("no maximo", 8), ("interesse", 6), ("interessado", 6),
        ("frente:", 4), ("riserva golf", 2), ("opcao", 2), ("milhões", 4),
        ("barramares", 4),
    ],
}

USELESS_PATTERNS = [
    r"^(ola|oi|bom dia|boa tarde|boa noite)\s*$",
    r"^https?://[^\s]+\s*$",
    r"^\w+\.(pdf|jpg|jpeg|png|doc|docx)\s*$",
]

RENTAL_KEYWORDS = ["locacao", "locação", "aluguel", "aluga", "alugar"]