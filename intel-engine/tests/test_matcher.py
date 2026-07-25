# test_matcher.py
from graphs.neo4j_client import GraphClient
import time

def run_tests():
    cliente = GraphClient()
    cliente.test_connection()
    
    # Mock de um Vendedor oferecendo imóvel
    vendedor_mock = {
        "original_content": {
            "author_phone": "5511999999999",
            "author_name": "João Corretor",
            "message_id": f"msg_venda_{int(time.time())}",
            "timestamp": int(time.time())
        },
        "intent": "oferece",
        "raw_text": "Vendo lindo apartamento no Centro, 2 quartos, 300 mil",
        "neighborhood": ["Centro"],
        "property_type": "Apartamento",
        "price": 300000.0,
        "bedrooms": 2,
        "area_m2": 70,
        "parking_spots": 1,
        "seafront": False
    }

    # Mock de um Comprador buscando imóvel
    comprador_mock = {
        "original_content": {
            "author_phone": "5511888888888",
            "author_name": "Maria Compradora",
            "message_id": f"msg_compra_{int(time.time())}",
            "timestamp": int(time.time())
        },
        "intent": "busca",
        "raw_text": "Procuro ap no Centro até 350 mil com pelo menos 2 quartos",
        "neighborhood": ["Centro"],
        "property_type": "Apartamento",
        "price": 350000.0,
        "bedrooms": 2,
        "area_m2": None,
        "parking_spots": None,
        "seafront": False
    }

    print("\n[+] Ingerindo dados de teste...")
    cliente.ingest_ad(vendedor_mock)
    cliente.ingest_ad(comprador_mock)
    
    print("\n[+] Executando Matcher...")
    resultados = cliente.match_opportunities()
    
    if resultados:
        print(f"✅ {len(resultados)} Match(es) encontrado(s)!")
        for match in resultados:
            print(f"  -> {match['Comprador']} quer comprar no {match['Bairro']} (Budget: {match['Orcamento']})")
            print(f"  -> {match['Vendedor']} está vendendo por {match['ValorVenda']}")
    else:
        print("❌ Nenhum match encontrado. Verifique as regras.")

    cliente.close()

if __name__ == "__main__":
    run_tests()