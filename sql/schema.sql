-- ==============================================================================
-- BLOCO 1: O INVENTÁRIO (Modelagem adaptada para PostgreSQL)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS Proprietarios (
    ProprietarioID SERIAL PRIMARY KEY,
    Nome           VARCHAR(255) NOT NULL,
    Telefone       VARCHAR(50) NOT NULL,
    Email          VARCHAR(255) NULL
);

CREATE TABLE IF NOT EXISTS Bairros (
    BairroID   SERIAL PRIMARY KEY,
    Nome       VARCHAR(255) NOT NULL,
    BairroZona VARCHAR(50) NOT NULL CHECK (BairroZona IN (
        'Zona Oeste', 'Zona Sudoeste', 'Zona Sul', 'Zona Norte'
    ))
);

CREATE TABLE IF NOT EXISTS Condominios (
    CondominioID   SERIAL PRIMARY KEY,
    Nome           VARCHAR(255) NOT NULL,
    Endereco       TEXT,
    Infraestrutura TEXT,
    BairroID       INTEGER NOT NULL,
    FOREIGN KEY (BairroID) REFERENCES Bairros (BairroID)
);

CREATE TABLE IF NOT EXISTS Imoveis (
    ImovelID        SERIAL PRIMARY KEY,
    CondominioID    INTEGER NULL,
    Tipologia       VARCHAR(50) NOT NULL CHECK (Tipologia IN ('Apartamento', 'Casa', 'Cobertura', 'Studio')),
    Quartos         INTEGER NOT NULL,
    Vagas           INTEGER DEFAULT 0,
    Valor           NUMERIC(15, 2) NOT NULL,
    ValorCondominio NUMERIC(15, 2) NOT NULL,
    IPTU            NUMERIC(15, 2) NOT NULL,
    Metragem        NUMERIC(10, 2) NOT NULL,
    Sol             VARCHAR(20) CHECK (Sol IS NULL OR Sol IN ('Manhã', 'Tarde', 'Passante')),
    BairroID        INTEGER NOT NULL,
    Endereco        TEXT NOT NULL,
    Descricao       TEXT NOT NULL,
    ImovelStatus    VARCHAR(50) NOT NULL DEFAULT 'Disponível' CHECK (ImovelStatus IN (
        'Disponível', 'Vendido', 'Alugado', 'Retirado de Venda'
    )),
    DataVenda       TIMESTAMP,
    DataCadastro    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ProprietarioID  INTEGER NOT NULL,
    CaminhoDrive    TEXT,
    LinkPublico     TEXT,
    FOREIGN KEY (BairroID)       REFERENCES Bairros (BairroID),
    FOREIGN KEY (CondominioID)   REFERENCES Condominios (CondominioID),
    FOREIGN KEY (ProprietarioID) REFERENCES Proprietarios (ProprietarioID)
);

CREATE TABLE IF NOT EXISTS Fotos (
    FotoID         SERIAL PRIMARY KEY,
    ImovelID       INTEGER NOT NULL,
    CaminhoArquivo TEXT NOT NULL UNIQUE,
    Principal      BOOLEAN DEFAULT FALSE,
    DataCadastro   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ImovelID) REFERENCES Imoveis (ImovelID) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Auditoria_Imoveis (
    LogID          SERIAL PRIMARY KEY,
    ImovelID       INTEGER NOT NULL,
    Operacao       VARCHAR(50) NOT NULL,
    ColunaAlterada VARCHAR(255),
    ValorAntigo    TEXT,
    ValorNovo      TEXT,
    DataHora       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==============================================================================
-- BLOCO 2: AS REGRAS DE NEGÓCIO E TRIGGERS (PL/pgSQL)
-- ==============================================================================

CREATE OR REPLACE FUNCTION log_imovel_insert_func()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO Auditoria_Imoveis (ImovelID, Operacao, ColunaAlterada, ValorNovo)
    VALUES (NEW.ImovelID, 'INSERT', 'Tudo', 'Imóvel cadastrado com sucesso');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER log_imovel_insert
AFTER INSERT ON Imoveis
FOR EACH ROW EXECUTE FUNCTION log_imovel_insert_func();

CREATE OR REPLACE FUNCTION log_imovel_update_status_func()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.ImovelStatus IS DISTINCT FROM NEW.ImovelStatus THEN
        INSERT INTO Auditoria_Imoveis (ImovelID, Operacao, ColunaAlterada, ValorAntigo, ValorNovo)
        VALUES (OLD.ImovelID, 'UPDATE', 'ImovelStatus', OLD.ImovelStatus, NEW.ImovelStatus);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER log_imovel_update_status
AFTER UPDATE OF ImovelStatus ON Imoveis
FOR EACH ROW EXECUTE FUNCTION log_imovel_update_status_func();

-- ==============================================================================
-- BLOCO 3: O SENTINEL BOT
-- ==============================================================================

-- Tabelas de agendamento (mantidas iguais ao SQLite)
CREATE TABLE IF NOT EXISTS Dispatched_Today (
    ImovelID    INTEGER NOT NULL,
    Instance    VARCHAR(100) NOT NULL,
    Reserved_At DATE NOT NULL,
    PRIMARY KEY (ImovelID, Reserved_At),
    FOREIGN KEY (ImovelID) REFERENCES Imoveis (ImovelID)
);

CREATE TABLE IF NOT EXISTS Dispatch_Cycle (
    ImovelID    INTEGER NOT NULL,
    Instance    VARCHAR(100) NOT NULL,
    SentAt      DATE NOT NULL,
    PRIMARY KEY (ImovelID, Instance),
    FOREIGN KEY (ImovelID) REFERENCES Imoveis (ImovelID)
);

-- Tabela de ingestão do WhatsApp (Substitui o messages.jsonl)
CREATE TABLE raw_messages (
    message_id VARCHAR(255) PRIMARY KEY,
    group_id VARCHAR(255),
    group_name VARCHAR(255),
    author_id VARCHAR(255),
    author_name VARCHAR(255),
    author_phone VARCHAR(50),
    message TEXT NOT NULL,
    ad_hash VARCHAR(255) UNIQUE,
    timestamp BIGINT,
    
    -- Controle do engine.py
    status VARCHAR(20) DEFAULT 'PENDING',
    normalized_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- A PONTE: Tabela de oportunidades cruzando WhatsApp com o Inventário
CREATE TABLE opportunities (
    opportunity_id SERIAL PRIMARY KEY,
    buyer_message_id VARCHAR(255) REFERENCES raw_messages(message_id) ON DELETE CASCADE,
    matched_imovel_id INTEGER REFERENCES Imoveis(ImovelID) ON DELETE CASCADE,
    match_score NUMERIC(5, 2),
    dispatch_status VARCHAR(20) DEFAULT 'QUEUED',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==============================================================================
-- BLOCO 4: ÍNDICES DE ALTA PERFORMANCE
-- ==============================================================================
CREATE INDEX idx_imoveis_bairro   ON Imoveis (BairroID);
CREATE INDEX idx_imoveis_status   ON Imoveis (ImovelStatus);
CREATE INDEX idx_raw_messages_status ON raw_messages(status);
CREATE INDEX idx_opportunities_dispatch ON opportunities(dispatch_status);