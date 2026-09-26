# Pipeline de Dados — Viagens a Serviço (Portal da Transparência)

Pipeline de dados ponta a ponta em **Python + PostgreSQL**, seguindo a **Arquitetura Medallion**
(Raw → Silver → Gold), construído para transformar os dados brutos de Viagens a Serviço do
Governo Federal em métricas e gráficos confiáveis para tomada de decisão.

## 1. Qual problema ele resolve

O Portal da Transparência publica os dados de viagens a serviço em sua forma bruta: textos com
vírgula como separador decimal, datas em formato `DD/MM/AAAA`, colunas soltas em 4 arquivos CSV
sem nenhuma relação declarada entre si. Isso torna qualquer análise lenta e sujeita a erro.

Este projeto automatiza todo o caminho — da extração à análise — respondendo perguntas de
negócio reais sobre o gasto público com viagens, como:

- Quais órgãos mais gastam?
- Quais destinos têm o maior custo médio por viagem?
- Qual foi a viagem mais longa e quanto ela custou?
- Qual tipo de pagamento tem o maior valor médio?
- Qual o meio de transporte mais usado?
- Qual UF de destino concentra mais trechos?
- Qual órgão pagou mais no total?

## 2. Arquitetura

```mermaid
flowchart LR
    A[Google Drive\n.zip com 4 CSVs] -->|1_extrair.py| B[(Camada Raw\nVARCHAR puro)]
    B -->|2_transformar.py| C[(Camada Silver\ntipada + PK/FK)]
    C -->|3_analise.ipynb| D[(Camada Gold\ntabela + view)]
    D --> E[Gráficos e\ninsights de negócio]
```

| Camada | O que é | Onde fica |
|---|---|---|
| **Raw** | Cópia fiel do CSV, todas as colunas `VARCHAR`, sem constraints | `raw_viagem`, `raw_pagamento`, `raw_passagem`, `raw_trecho` |
| **Silver** | Dados limpos e tipados (`DECIMAL`, `DATE`), com `PK`/`FK`/constraints | `silver_viagem`, `silver_pagamento`, `silver_passagem`, `silver_trecho` |
| **Gold** | Métricas de negócio agregadas (tabela **e** view) | `gold_resumo_orgao` / `vw_resumo_orgao` |

## 3. Técnicas e tecnologias utilizadas

- **Python 3** — extração, tratamento e carga dos dados (`pandas`, `psycopg2`, `gdown`)
- **PostgreSQL** — banco relacional das 3 camadas Medallion (Raw, Silver, Gold)
- **SQL puro** — `CREATE TABLE` com `PRIMARY KEY`, `FOREIGN KEY`, `CHECK`, `UNIQUE`, `NOT NULL`;
  `JOIN` + `GROUP BY` para a camada Gold; `VIEW` para reuso de consultas
  - **Jupyter Notebook** — análise exploratória, respostas às perguntas de negócio e gráficos (`matplotlib`)
- **python-dotenv (implementação própria em `config.py`)** — leitura de credenciais via `.env`
- **Git/GitHub** — versionamento do código com commits e branches por funcionalidade

## 4. Estrutura do repositório

```
.
├── .env.example         # modelo de credenciais (copie para .env)
├── .gitignore            # ignora .env, .zip, .csv, data/
├── requirements.txt      # dependências do projeto
├── config.py             # parâmetros do projeto + leitura do .env
├── banco.py              # conexão e funções utilitárias do PostgreSQL
├── 0_criar_banco.sql     # cria o database e as 8 tabelas (Raw + Silver)
├── 1_extrair.py          # baixa o zip do Drive + carga na camada Raw
├── 2_transformar.py      # limpeza/tipagem Raw -> Silver + colunas calculadas
├── 3_analise.ipynb       # camada Gold + 7 perguntas de negócio + gráficos
└── data/                 # csvs/zip baixados (ignorado pelo Git)
```

## 5. Como executar

### Pré-requisitos
- Python 3.10+
- PostgreSQL instalado e rodando localmente (ou acessível remotamente)
- Uma conta no Google Drive com o `.zip` dos 4 CSVs compartilhado como "Qualquer pessoa com o link"

### Passo a passo

1. **Clone o repositório e instale as dependências**
   ```bash
   git clone <url-do-seu-repositorio>
   cd <pasta-do-repositorio>
   pip install -r requirements.txt
   ```

2. **Configure as credenciais**
   ```bash
   cp .env.example .env
   # edite o .env com o usuário/senha do seu PostgreSQL
   ```

3. **Preencha o `DRIVE_FILE_ID` em `config.py`**
   Abra o arquivo `.zip` no seu Google Drive → "Compartilhar" → "Qualquer pessoa com o link" →
   copie o trecho do link entre `/d/` e `/view` e cole em `DRIVE_FILE_ID`.

4. **Crie o banco e as tabelas**
   ```bash
   psql -U postgres -h localhost -f 0_criar_banco.sql
   ```

5. **Rode a extração (Raw)**
   ```bash
   python 1_extrair.py
   ```

6. **Rode a transformação (Silver)**
   ```bash
   python 2_transformar.py
   ```

7. **Abra o notebook e rode a análise (Gold)**
   ```bash
   jupyter notebook 3_analise.ipynb
   ```
   Execute todas as células (`Run All`). O notebook cria a tabela e a view `gold_resumo_orgao`
   / `vw_resumo_orgao`, responde as 7 perguntas de negócio e gera os gráficos.

## 6. Conclusões e insights

- O gasto com viagens a serviço é fortemente concentrado em poucos órgãos — o ranking de maior
  custo total (camada Silver) e de maior valor pago (camada Gold) aponta consistentemente para
  os mesmos órgãos, o que reforça a confiabilidade do pipeline.
- O transporte aéreo domina os trechos registrados, coerente com viagens interestaduais de longa
  distância.
- Alguns destinos apresentam custo médio elevado mesmo com poucas viagens recorrentes, o que pode
  indicar rotas com menor oferta de passagens ou viagens de maior duração.
- Consolidar a camada Gold como tabela **e** view permite tanto consultas rápidas (tabela
  materializada) quanto sempre-atualizadas (view), dependendo da necessidade de quem for consumir
  o dado.

## 7. Melhorias futuras

- Adicionar dimensão de tempo (mês/trimestre) para analisar sazonalidade dos gastos.
- Cruzar com dados de servidores públicos para identificar concentração de viagens por pessoa/cargo.
- Adicionar testes automatizados (ex.: `pytest`) para as funções de conversão de tipos.
- Orquestrar o pipeline com Airflow ou cron, em vez de execução manual dos 3 scripts.
- Publicar a camada Gold em um dashboard (Streamlit/Power BI) para consumo por não-técnicos.
