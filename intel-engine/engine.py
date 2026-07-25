import time
import json
import pika
import os
from pathlib import Path

from classifier import run_classifier
from normalizer import run_normalizer
from graphs.neo4j_client import GraphClient

from database import (
    get_message_by_id,
    get_property_details, 
    update_message_status, 
    save_opportunities
)

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "localhost")

def process_message(ch, method, properties, body):
    """Callback disparado instantaneamente quando uma nova mensagem chega na fila."""
    event_data = json.loads(body)
    msg_id = event_data.get("message_id")
    
    msg_data = get_message_by_id(msg_id)
    
    if not msg_data:
        print(f"[ENGINE] Mensagem {msg_id} não encontrada no BD. Ignorando.")
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    try:
        # 1. Processamento NLP (Transforma a mensagem única numa lista para manter compatibilidade)
        sellers, buyers, useless = run_classifier([msg_data])
        sellers_pad, buyers_pad = run_normalizer(sellers, buyers)
        self_ads = get_property_details()

        # 2. Ingestão e Matching no Grafo (Neo4j)
        graph = GraphClient()
        try:
            for ad in sellers_pad + buyers_pad + self_ads:
                graph.ingest_ad(ad)
            
            opportunities = graph.match_opportunities() 
        except Exception as e:
            print(f"[GRAPH] Erro nas operações do grafo: {e}")
            opportunities = []
        finally:
            graph.close()

        # 3. Salva e Publica Novos Matches
        if opportunities:
            opp_ids = save_opportunities(opportunities)
            
            # Publica cada nova oportunidade na fila do Egress
            for opp_id in opp_ids:
                ch.basic_publish(
                    exchange='',
                    routing_key='opportunities_queue',
                    body=json.dumps({"opportunity_id": opp_id}),
                    properties=pika.BasicProperties(delivery_mode=2) # Mensagem persistente
                )
            print(f"[MATCH] {len(opp_ids)} novas oportunidades detectadas e enviadas para o Egress!")

        # 4. Atualiza o status no banco
        pad_data_map = {ad["original_content"]["message_id"]: ad for ad in sellers_pad + buyers_pad}
        norm_data = pad_data_map.get(msg_id)
        update_message_status(msg_id, "PROCESSED", normalized_data=norm_data)
        
        print(f"[ENGINE] Mensagem {msg_id} processada com sucesso.")
        
        # 5. Confirma o processamento para o RabbitMQ remover da fila
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print(f"[ENGINE ERRO CRÍTICO] Falha ao processar {msg_id}: {e}")
        # Nack sem requeue manda a mensagem para uma Dead Letter Queue (se configurada) ou descarta
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def main():
    print("="*60)
    print("[ENGINE] Conectando ao RabbitMQ...")
    print("="*60)
    
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_URL))
    channel = connection.channel()

    # Garante que as filas existem
    channel.queue_declare(queue='raw_messages', durable=True)
    channel.queue_declare(queue='opportunities_queue', durable=True)

    # basic_qos garante que o engine pegue 1 mensagem por vez (Fair Dispatch)
    channel.basic_qos(prefetch_count=1)
    
    channel.basic_consume(queue='raw_messages', on_message_callback=process_message)
    
    print("[ENGINE] Worker ativo. Aguardando mensagens...")
    channel.start_consuming()

if __name__ == '__main__':
    main()