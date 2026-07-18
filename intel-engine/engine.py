import json
import time

from pathlib import Path

from classifier import run_classifier
from cleaner import (
    clean_and_dedup_messages,
    clean_and_dedup_opportunities,
    clean_and_dedup_self_opportunities,
    dedup_dispatch_state,
    reconcile_engine_state,
)

from database import (
    get_pending_messages, 
    get_property_details, 
    update_message_status, 
    save_opportunities
)

from egest import export_opportunities, export_self_opportunities
from matcher import get_opportunity
from normalizer import run_normalizer, run_self_normalizer

from graphs.neo4j_client import GraphClient

BASE_DIR = Path(__file__).resolve().parent.parent

# Intervalo entre execuções do cleaner. Não roda a cada iteração do loop
# (a cada 3s) porque cleaner.py reescreve os .jsonl inteiros — caro demais
# pra rodar com essa frequência.
CLEANUP_INTERVAL_SECONDS = 3600  # 1 hora


def run_cleanup():
    print(f"[ENGINE] Rodando limpeza periódica ({time.strftime('%Y-%m-%d %H:%M:%S')})")
    clean_and_dedup_messages()
    clean_and_dedup_opportunities()
    clean_and_dedup_self_opportunities()
    reconcile_engine_state()
    dedup_dispatch_state()


last_cleanup = 0.0

while True:
    # 1. Lê a fila do banco de dados (Substitui o read_new_messages)
    new_messages = get_pending_messages()

    if new_messages:
        try:
            # 2. Processamento NLP
            sellers, buyers, useless = run_classifier(new_messages)
            sellers_pad, buyers_pad = run_normalizer(sellers, buyers)
            self_ads = run_self_normalizer(get_property_details())

            print(f"-> Vendedores encontrados: {len(sellers_pad)}")
            print(f"-> Compradores encontrados: {len(buyers_pad)}")

            # 3. Ingestão no Grafo (Neo4j)
            print("[GRAPH] Iniciando ingestão no Neo4j...")
            try:
                graph = GraphClient()
                for seller in sellers_pad:
                    graph.ingest_ad(seller)
                for buyer in buyers_pad:
                    graph.ingest_ad(buyer)
                for self_ad in self_ads:
                    graph.ingest_ad(self_ad)
                graph.close()
                print("[GRAPH] Ingestão concluída com sucesso!")
            except Exception as e:
                print(f"[GRAPH] Erro ao salvar no grafo: {e}")

            # 4. Matching Semântico
            self_opportunities = get_opportunity(self_ads, buyers_pad)

            # 5. Salva as oportunidades (Substitui o export_self_opportunities)
            if self_opportunities:
                save_opportunities(self_opportunities)
                print(f"[MATCH] {len(self_opportunities)} oportunidades salvas na fila de envio!")

            # 6. Atualiza o status das mensagens processadas com sucesso no banco
            # (Substitui o save_state)
            
            # Cria um dicionário rápido para achar os dados normalizados pelo message_id
            pad_data_map = {ad["original_content"]["message_id"]: ad for ad in sellers_pad + buyers_pad}

            for msg in new_messages:
                msg_id = msg["message_id"]
                norm_data = pad_data_map.get(msg_id)
                # Se não tem norm_data, é porque foi classificada como useless
                update_message_status(msg_id, "PROCESSED", normalized_data=norm_data)

            print("Lote processado com sucesso:", len(new_messages))

        except Exception as e:
            print(f"[ENGINE ERRO CRÍTICO] Falha ao processar lote de mensagens: {e}")
            # Em caso de erro grave, as mensagens continuam como 'PENDING' no banco
            # e o bot tentará processar novamente no próximo ciclo.

  #  if time.time() - last_cleanup >= CLEANUP_INTERVAL_SECONDS:
   #      run_cleanup()
    #    last_cleanup = time.time()

    time.sleep(3)