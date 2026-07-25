import time

from pathlib import Path

from classifier import run_classifier
from normalizer import run_normalizer
from graphs.neo4j_client import GraphClient

from database import (
    get_pending_messages, 
    get_property_details, 
    update_message_status, 
    save_opportunities
)

# Agora importamos APENAS as novas funções de limpeza de banco
from cleaner import purge_old_data_neo4j, purge_old_data_sql

BASE_DIR = Path(__file__).resolve().parent.parent
CLEANUP_INTERVAL_SECONDS = 3600

def run_cleanup():
    print(f"[ENGINE] Rodando limpeza periódica de bancos de dados ({time.strftime('%Y-%m-%d %H:%M:%S')})")
    
    # Adicionamos o expurgo nos bancos de dados respeitando a regra de negócio:
    # 90 dias para ofertas (imóveis) e 30 dias para procuras (compradores)
    limite_90d = int(time.time()) - (90 * 24 * 60 * 60)
    limite_30d = int(time.time()) - (30 * 24 * 60 * 60)
    
    # O PostgreSQL guarda o histórico bruto, usamos o maior prazo (90 dias) para apagar a linha da tabela
    purge_old_data_sql(limite_90d)
    
    # O Neo4j expurga arestas específicas baseado no prazo de cada tipo
    purge_old_data_neo4j(limite_30d, limite_90d)

last_cleanup = 0.0

while True:

    new_messages = get_pending_messages()

    if new_messages:
        try:
            # 1. Processamento NLP
            sellers, buyers, useless = run_classifier(new_messages)
            sellers_pad, buyers_pad = run_normalizer(sellers, buyers)
            self_ads = get_property_details()

            print(f"-> Vendedores encontrados: {len(sellers_pad)}")
            print(f"-> Compradores encontrados: {len(buyers_pad)}")

            # 2. Ingestão e Matching no Grafo (Neo4j)
            print("[GRAPH] Iniciando operações no Neo4j...")
            graph = GraphClient()
            try:
                for ad in sellers_pad + buyers_pad + self_ads:
                    graph.ingest_ad(ad)
                
                print("[GRAPH] Ingestão concluída! Buscando matches semânticos...")
                # Substitui a chamada get_opportunity() do matcher.py antigo
                opportunities = graph.match_opportunities() 
                
            except Exception as e:
                print(f"[GRAPH] Erro nas operações do grafo: {e}")
                opportunities = []
            finally:
                graph.close()

            # 3. Salva as oportunidades (seja de terceiros ou self)
            if opportunities:
                save_opportunities(opportunities)
                print(f"[MATCH] {len(opportunities)} oportunidades salvas na fila de envio!")

            # 4. Atualiza o status no banco
            pad_data_map = {ad["original_content"]["message_id"]: ad for ad in sellers_pad + buyers_pad}

            for msg in new_messages:
                msg_id = msg["message_id"]
                norm_data = pad_data_map.get(msg_id)
                update_message_status(msg_id, "PROCESSED", normalized_data=norm_data)

            print("Lote processado com sucesso:", len(new_messages))

        except Exception as e:
            print(f"[ENGINE ERRO CRÍTICO] Falha ao processar lote: {e}")

    # Descomente e ajuste a indentação se quiser ativar a limpeza periódica
    # if time.time() - last_cleanup >= CLEANUP_INTERVAL_SECONDS:
    #     run_cleanup()
    #     last_cleanup = time.time()

    time.sleep(3)