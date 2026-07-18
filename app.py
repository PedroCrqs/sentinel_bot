import streamlit as st
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv, find_dotenv

st.set_page_config(page_title="Sentinela - Radar de Oportunidades", layout="wide")

# 1. Injetando CSS Minimalista e Editorial
st.markdown("""
    <style>
    /* Fundo clean e fonte elegante */
    .stApp {
        background-color: #FAFAFA;
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    }
    
    /* Títulos suaves */
    h1, h2, h3 {
        color: #2C3E50;
        font-weight: 300;
        letter-spacing: -0.5px;
    }
    
    /* Cards de Match com sombra sutil e bordas arredondadas */
    div[data-testid="stVerticalBlock"] div[style*="flex-direction: column;"] > div[data-testid="stVerticalBlock"] {
        background-color: #FFFFFF;
        padding: 24px;
        border-radius: 12px;
        box-shadow: 0px 4px 20px rgba(0, 0, 0, 0.03);
        border: 1px solid #F0F0F0;
    }
    
    /* Estilo para tags (Bairro) */
    .bairro-tag {
        display: inline-block;
        background-color: #EEF2F5;
        color: #5C6E80;
        padding: 4px 12px;
        border-radius: 16px;
        font-size: 0.85rem;
        font-weight: 500;
        margin-bottom: 16px;
    }
    
    /* Botão sutil e elegante */
    .stButton > button {
        background-color: #2C3E50;
        color: white;
        border-radius: 6px;
        border: none;
        padding: 10px 24px;
        font-weight: 500;
        transition: all 0.2s ease-in-out;
        width: 100%;
    }
    .stButton > button:hover {
        background-color: #1A252F;
        box-shadow: 0px 4px 12px rgba(44, 62, 80, 0.2);
    }
    </style>
""", unsafe_allow_html=True)

# 2. Conexão com o Banco de Dados
load_dotenv(find_dotenv())
URI = os.getenv("NEO4J_URI", "")
USER = os.getenv("NEO4J_USERNAME", "")
PASSWORD = os.getenv("NEO4J_PASSWORD", "")

@st.cache_resource
def get_driver():
    return GraphDatabase.driver(URI, auth=(USER, PASSWORD))

def buscar_matches():
    """Roda a query Cypher de colisão entre Oferta e Demanda no mesmo bairro"""
    query = """
    MATCH (c:Pessoa)-[:ENVIOU]->(mc:Mensagem)-[:BUSCA]->(i_busca:Imovel)-[:LOCALIZADO_EM]->(b:Bairro)
    MATCH (v:Pessoa)-[:ENVIOU]->(mv:Mensagem)-[:OFERECE]->(i_oferta:Imovel)-[:LOCALIZADO_EM]->(b)
    WHERE c <> v
    RETURN c.nome AS Comprador, c.telefone AS Tel_Comprador,
           v.nome AS Vendedor, v.telefone AS Tel_Vendedor,
           b.nome AS Bairro, i_oferta.preco AS Preco, 
           i_oferta.quartos AS Quartos, i_oferta.tipo AS Tipo
    LIMIT 20
    """
    driver = get_driver()
    try:
        with driver.session() as session:
            resultados = session.run(query).data()
        return resultados
    except Exception as e:
        # Se o banco disser que a seta ainda não existe, retornamos vazio em silêncio.
        return []
    

# 3. Interface Visual
st.title("Sentinela - Radar de Oportunidades")
st.markdown("Identificação inteligente de *matches* imobiliários baseada em interseções de rede.")
st.write("---")

matches = buscar_matches()

if not matches:
    st.info("Nenhum match encontrado no momento. Aguarde a entrada de novos dados na rede.")
else:
    # Para cada match, criamos uma "linha" visual com duas colunas
    for match in matches:
        bairro = match["Bairro"]
        
        # Container do Match
        with st.container():
            st.markdown(f"<div class='bairro-tag'>📍 {bairro}</div>", unsafe_allow_html=True)
            
            col_esq, col_dir, col_acao = st.columns([2, 2, 1])
            
            # Card da Demanda (Comprador)
            with col_esq:
                st.subheader("Demanda")
                st.markdown(f"**Cliente:** {match['Comprador']}")
                st.markdown(f"**Contato:** {match['Tel_Comprador']}")
                st.caption("Buscando imóvel na região.")
                
            # Card da Oferta (Vendedor)
            with col_dir:
                st.subheader("Oferta")
                st.markdown(f"**Corretor/Proprietário:** {match['Vendedor']}")
                st.markdown(f"**Imóvel:** {match.get('Tipo', 'Imóvel')} - {match.get('Quartos', '-')} Quartos")
                
                preco = match.get('Preco')
                preco_formatado = f"R$ {preco:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if preco else "Sob consulta"
                st.markdown(f"**Valor:** {preco_formatado}")
            
            # Ação de Conexão
            with col_acao:
                st.write("") # Espaçamento
                st.write("")
                if st.button("Gerar Conexão", key=f"{match['Tel_Comprador']}_{match['Tel_Vendedor']}"):
                    st.success("Mensagem pronta para envio!")
                    
        st.write("---") # Linha divisória suave entre os matches