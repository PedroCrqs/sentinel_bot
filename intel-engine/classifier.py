from ingest import data

sellers = []
buyers = []
uselesses = []
seller_filter = ['vendo', '*R$', 'R$', 'localizado', 'fica no', 'oportunidade', 'venda']
buyer_filter = ['compro', 'busco', 'procuro', 'cliente', 'preciso']

class Selling:
    def __init__(self, data_line):
        self.seller = data_line
        self.stats = f'Corretor: {self.seller['author_name']}\nTelefone: {self.seller['author_phone']}\nAnúncio: {self.seller['message']} '
        
class Buying:
    def __init__(self, data_line):
        self.buyer = data_line
        self.stats = f'Corretor: {self.buyer['author_name']}\nTelefone: {self.buyer['author_phone']}\nPedido: {self.buyer['message']}\n\n\n '

class Useless:
    def __init__(self, data_line):
        self.useless = data_line
        self.stats = f'Corretor: {self.useless['author_name']}\nTelefone: {self.useless['author_phone']}\nConteúdo: {self.useless['message']}\n\n\n '

for line in data:
    message = line.get('message', '').lower()
    if any(keyword in message for keyword in seller_filter):
        sellers.append(Selling(line))
    elif any(keyword in message for keyword in buyer_filter):
        buyers.append(Buying(line))
    else:
        uselesses.append(Useless(line))    

# print(useless[0])

for useless in uselesses:
    print(useless.stats)
     

