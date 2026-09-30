-- =============================================================================
-- 0_criar_banco.sql
-- Cria o database "transparencia" e as 8 tabelas do pipeline (Arquitetura
-- Medallion: 4 tabelas RAW + 4 tabelas SILVER), seguindo o dicionário de
-- dados do projeto avaliativo.
--
-- COMO RODAR (psql):
--   1) Conecte-se ao Postgres em um database já existente (ex.: postgres):
--        psql -U postgres -h localhost
--   2) Rode este arquivo inteiro:
--        \i 0_criar_banco.sql
--   OU direto do terminal (fora do psql), em duas etapas:
--        psql -U postgres -h localhost -c "CREATE DATABASE transparencia;"
--        psql -U postgres -h localhost -d transparencia -f 0_criar_banco.sql
--      (nesse caso comente/apague a linha CREATE DATABASE abaixo, pois já
--      foi criado na primeira chamada)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Criação do banco (rode esta linha isolada se estiver usando \i completo)
-- ---------------------------------------------------------------------------
CREATE DATABASE transparencia;

-- Depois de criar o banco, conecte-se a ele antes de continuar:
\c transparencia

-- =============================================================================
-- CAMADA RAW
-- Cópia fiel dos CSVs: todas as colunas em VARCHAR, sem nenhuma constraint,
-- preservando exatamente o dado bruto (vírgula decimal, data DD/MM/AAAA etc.)
-- =============================================================================

DROP TABLE IF EXISTS raw_trecho;
DROP TABLE IF EXISTS raw_passagem;
DROP TABLE IF EXISTS raw_pagamento;
DROP TABLE IF EXISTS raw_viagem;

-- -----------------------------------------------------------------------
-- raw_viagem  (espelha 2025_Viagem.csv)
-- -----------------------------------------------------------------------
CREATE TABLE raw_viagem (
    id_viagem               VARCHAR(50),
    num_proposta            VARCHAR(50),
    situacao                VARCHAR(100),
    viagem_urgente          VARCHAR(20),
    justificativa_urgencia  VARCHAR(4000),
    cod_orgao_superior      VARCHAR(50),
    nome_orgao_superior     VARCHAR(255),
    cod_orgao_solicitante   VARCHAR(50),
    nome_orgao_solicitante  VARCHAR(255),
    cpf_viajante            VARCHAR(50),
    nome_viajante           VARCHAR(255),
    cargo                   VARCHAR(255),
    funcao                  VARCHAR(255),
    descricao_funcao        VARCHAR(255),
    data_inicio             VARCHAR(20),
    data_fim                VARCHAR(20),
    destinos                VARCHAR(4000),
    motivo                  VARCHAR(4000),
    valor_diarias           VARCHAR(50),
    valor_passagens         VARCHAR(50),
    valor_devolucao         VARCHAR(50),
    valor_outros_gastos     VARCHAR(50)
);

-- -----------------------------------------------------------------------
-- raw_pagamento  (espelha 2025_Pagamento.csv)
-- -----------------------------------------------------------------------
CREATE TABLE raw_pagamento (
    id_viagem            VARCHAR(50),
    num_proposta         VARCHAR(50),
    cod_orgao_superior   VARCHAR(50),
    nome_orgao_superior  VARCHAR(255),
    cod_orgao_pagador    VARCHAR(50),
    nome_orgao_pagador   VARCHAR(255),
    cod_ug_pagadora      VARCHAR(50),
    nome_ug_pagadora     VARCHAR(255),
    tipo_pagamento       VARCHAR(100),
    valor                VARCHAR(50)
);

-- -----------------------------------------------------------------------
-- raw_passagem  (espelha 2025_Passagem.csv)
-- -----------------------------------------------------------------------
CREATE TABLE raw_passagem (
    id_viagem             VARCHAR(50),
    num_proposta          VARCHAR(50),
    meio_transporte       VARCHAR(50),
    pais_origem_ida       VARCHAR(100),
    uf_origem_ida         VARCHAR(100),
    cidade_origem_ida     VARCHAR(150),
    pais_destino_ida      VARCHAR(100),
    uf_destino_ida        VARCHAR(100),
    cidade_destino_ida    VARCHAR(150),
    pais_origem_volta     VARCHAR(100),
    uf_origem_volta       VARCHAR(100),
    cidade_origem_volta   VARCHAR(150),
    pais_destino_volta    VARCHAR(100),
    uf_destino_volta      VARCHAR(100),
    cidade_destino_volta  VARCHAR(150),
    valor_passagem        VARCHAR(50),
    taxa_servico          VARCHAR(50),
    data_emissao          VARCHAR(20),
    hora_emissao          VARCHAR(20)
);

-- -----------------------------------------------------------------------
-- raw_trecho  (espelha 2025_Trecho.csv)
-- -----------------------------------------------------------------------
CREATE TABLE raw_trecho (
    id_viagem          VARCHAR(50),
    num_proposta       VARCHAR(50),
    sequencia_trecho   VARCHAR(20),
    origem_data        VARCHAR(20),
    origem_pais        VARCHAR(100),
    origem_uf          VARCHAR(100),
    origem_cidade      VARCHAR(150),
    destino_data       VARCHAR(20),
    destino_pais       VARCHAR(100),
    destino_uf         VARCHAR(100),
    destino_cidade     VARCHAR(150),
    meio_transporte    VARCHAR(50),
    numero_diarias     VARCHAR(50),
    missao             VARCHAR(20)
);


-- =============================================================================
-- CAMADA SILVER
-- Dados limpos e tipados (DECIMAL, DATE), com PK, FK e constraints extras
-- declaradas dentro do próprio CREATE TABLE, conforme o dicionário de dados.
-- =============================================================================

DROP TABLE IF EXISTS silver_trecho;
DROP TABLE IF EXISTS silver_passagem;
DROP TABLE IF EXISTS silver_pagamento;
DROP TABLE IF EXISTS silver_viagem;

-- -----------------------------------------------------------------------
-- silver_viagem
-- Constraints extras: NOT NULL em nome_orgao_superior / CHECK valor_diarias >= 0
-- -----------------------------------------------------------------------
CREATE TABLE silver_viagem (
    id_viagem             VARCHAR(20)     NOT NULL,
    num_proposta          VARCHAR(20),
    situacao              VARCHAR(50),
    viagem_urgente        VARCHAR(5),
    cod_orgao_superior    VARCHAR(20),
    nome_orgao_superior   VARCHAR(255)    NOT NULL,
    nome_viajante         VARCHAR(255),
    cargo                 VARCHAR(255),
    data_inicio           DATE,
    data_fim               DATE,
    destinos              VARCHAR(4000),
    motivo                VARCHAR(4000),
    valor_diarias         DECIMAL(10,2)   CHECK (valor_diarias >= 0),
    valor_passagens       DECIMAL(10,2),
    valor_devolucao       DECIMAL(10,2),
    valor_outros_gastos   DECIMAL(10,2),
    valor_total           DECIMAL(12,2),
    duracao_dias          INT,
    CONSTRAINT pk_silver_viagem PRIMARY KEY (id_viagem)
);

-- -----------------------------------------------------------------------
-- silver_passagem
-- Constraints extras: CHECK valor_passagem >= 0 / CHECK taxa_servico >= 0
-- -----------------------------------------------------------------------
CREATE TABLE silver_passagem (
    id_passagem          INT GENERATED ALWAYS AS IDENTITY,
    id_viagem             VARCHAR(20)    NOT NULL,
    meio_transporte       VARCHAR(50),
    pais_origem_ida       VARCHAR(60),
    uf_origem_ida         VARCHAR(40),
    cidade_origem_ida     VARCHAR(80),
    pais_destino_ida      VARCHAR(60),
    uf_destino_ida        VARCHAR(40),
    cidade_destino_ida    VARCHAR(80),
    valor_passagem        DECIMAL(10,2)  CHECK (valor_passagem >= 0),
    taxa_servico          DECIMAL(10,2)  CHECK (taxa_servico >= 0),
    data_emissao          DATE,
    CONSTRAINT pk_silver_passagem PRIMARY KEY (id_passagem),
    CONSTRAINT fk_passagem_viagem FOREIGN KEY (id_viagem)
        REFERENCES silver_viagem (id_viagem)
);

-- -----------------------------------------------------------------------
-- silver_pagamento
-- Constraints extras: CHECK valor >= 0 / NOT NULL em tipo_pagamento
-- -----------------------------------------------------------------------
CREATE TABLE silver_pagamento (
    id_pagamento         INT GENERATED ALWAYS AS IDENTITY,
    id_viagem             VARCHAR(20)    NOT NULL,
    num_proposta          VARCHAR(20),
    nome_orgao_pagador    VARCHAR(255),
    nome_ug_pagadora      VARCHAR(255),
    tipo_pagamento        VARCHAR(50)    NOT NULL,
    valor                 DECIMAL(10,2)  CHECK (valor >= 0),
    CONSTRAINT pk_silver_pagamento PRIMARY KEY (id_pagamento),
    CONSTRAINT fk_pagamento_viagem FOREIGN KEY (id_viagem)
        REFERENCES silver_viagem (id_viagem)
);

-- -----------------------------------------------------------------------
-- silver_trecho
-- Constraints extras: CHECK numero_diarias >= 0 / UNIQUE (id_viagem, sequencia_trecho)
-- -----------------------------------------------------------------------
CREATE TABLE silver_trecho (
    id_trecho            INT GENERATED ALWAYS AS IDENTITY,
    id_viagem             VARCHAR(20)    NOT NULL,
    sequencia_trecho      INT,
    origem_data           DATE,
    origem_uf             VARCHAR(40),
    origem_cidade         VARCHAR(80),
    destino_data          DATE,
    destino_uf            VARCHAR(40),
    destino_cidade        VARCHAR(80),
    meio_transporte       VARCHAR(50),
    numero_diarias        DECIMAL(10,2)  CHECK (numero_diarias >= 0),
    CONSTRAINT pk_silver_trecho PRIMARY KEY (id_trecho),
    CONSTRAINT fk_trecho_viagem FOREIGN KEY (id_viagem)
        REFERENCES silver_viagem (id_viagem),
    CONSTRAINT uq_trecho_sequencia UNIQUE (id_viagem, sequencia_trecho)
);

-- =============================================================================
-- Fim do script. Confira com \dt se as 8 tabelas foram criadas.
-- =============================================================================
