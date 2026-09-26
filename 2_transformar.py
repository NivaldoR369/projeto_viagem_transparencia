"""
2_transformar.py
-----------------
Fase 2 do pipeline - Transformação e camada Silver.

O que este script faz:
    1) Lê cada tabela RAW (texto puro) em blocos.
    2) Converte texto -> DECIMAL (vírgula decimal "1272,97" -> 1272.97) e
       texto -> DATE ("25/01/2025" -> date(2025, 1, 25)).
    3) Calcula as colunas derivadas valor_total e duracao_dias.
    4) Respeita a integridade referencial: só insere em silver_pagamento,
       silver_passagem e silver_trecho as linhas cujo id_viagem já exista
       em silver_viagem (evita violar a FK e descarta registros órfãos).
    5) Deduplica id_viagem (PRIMARY KEY de silver_viagem) mantendo a
       primeira ocorrência.

Idempotência: cada tabela SILVER é truncada antes da carga (TRUNCATE ...
CASCADE em silver_viagem, para não deixar filhos órfãos de uma execução
anterior), então rodar o script de novo nunca duplica dados.
"""

import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

import banco
from config import PASTA_DADOS, TAMANHO_BLOCO  # noqa: F401 (mantido por padronização)


# ---------------------------------------------------------------------------
# Funções de conversão
# ---------------------------------------------------------------------------
def converter_decimal(texto):
    """'1272,97' -> Decimal('1272.97'). Valores vazios/estranhos viram None."""
    if texto is None:
        return None
    texto = texto.strip()
    if texto == "" or texto.lower() in ("sem informação", "nan", "none"):
        return None
    texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


def converter_data(texto):
    """'25/01/2025' -> date(2025, 1, 25). Valores vazios/estranhos viram None."""
    if texto is None:
        return None
    texto = texto.strip()
    if texto == "" or texto.lower() in ("sem informação", "nan", "none"):
        return None
    try:
        return datetime.strptime(texto, "%d/%m/%Y").date()
    except ValueError:
        return None


def converter_inteiro(texto):
    if texto is None:
        return None
    texto = texto.strip()
    if texto == "" or texto.lower() in ("sem informação", "nan", "none"):
        return None
    try:
        return int(Decimal(texto.replace(",", ".")))
    except InvalidOperation:
        return None


def limpar_texto(texto, tamanho_maximo=None):
    if texto is None:
        return None
    texto = texto.strip()
    if texto == "" or texto.lower() == "sem informação":
        return None
    if tamanho_maximo:
        texto = texto[:tamanho_maximo]
    return texto


# ---------------------------------------------------------------------------
# Leitura em blocos de uma tabela raw usando cursor server-side (não carrega
# a tabela inteira na memória de uma vez - importante para arquivos grandes)
# ---------------------------------------------------------------------------
def ler_raw_em_blocos(conexao, tabela: str, colunas: list[str]):
    nome_cursor = f"cursor_{tabela}"
    cursor = conexao.cursor(name=nome_cursor)
    cursor.itersize = TAMANHO_BLOCO
    cursor.execute(f"SELECT {', '.join(colunas)} FROM {tabela};")
    while True:
        bloco = cursor.fetchmany(TAMANHO_BLOCO)
        if not bloco:
            break
        yield bloco
    cursor.close()


# ---------------------------------------------------------------------------
# silver_viagem
# ---------------------------------------------------------------------------
def transformar_viagem(conexao_leitura, conexao_escrita) -> set:
    print("[transformar] silver_viagem...")
    banco.executar(conexao_escrita, "TRUNCATE TABLE silver_viagem CASCADE;")

    colunas_raw = [
        "id_viagem", "num_proposta", "situacao", "viagem_urgente",
        "cod_orgao_superior", "nome_orgao_superior", "nome_viajante", "cargo",
        "data_inicio", "data_fim", "destinos", "motivo",
        "valor_diarias", "valor_passagens", "valor_devolucao", "valor_outros_gastos",
    ]

    sql_insert = """
        INSERT INTO silver_viagem (
            id_viagem, num_proposta, situacao, viagem_urgente, cod_orgao_superior,
            nome_orgao_superior, nome_viajante, cargo, data_inicio, data_fim,
            destinos, motivo, valor_diarias, valor_passagens, valor_devolucao,
            valor_outros_gastos, valor_total, duracao_dias
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id_viagem) DO NOTHING;
    """

    ids_validos = set()
    total_inseridas = 0

    for bloco in ler_raw_em_blocos(conexao_leitura, "raw_viagem", colunas_raw):
        linhas = []
        for row in bloco:
            (id_viagem, num_proposta, situacao, viagem_urgente, cod_orgao_superior,
             nome_orgao_superior, nome_viajante, cargo, data_inicio, data_fim,
             destinos, motivo, valor_diarias, valor_passagens, valor_devolucao,
             valor_outros_gastos) = row

            id_viagem = limpar_texto(id_viagem, 20)
            nome_orgao_superior = limpar_texto(nome_orgao_superior, 255)

            # regras de negócio: PK e a constraint NOT NULL não podem ser nulas
            if not id_viagem or not nome_orgao_superior:
                continue
            if id_viagem in ids_validos:
                continue  # dedup do lado do Python também

            d_inicio = converter_data(data_inicio)
            d_fim = converter_data(data_fim)
            duracao_dias = (d_fim - d_inicio).days if (d_inicio and d_fim) else None

            v_diarias = converter_decimal(valor_diarias) or Decimal("0")
            v_passagens = converter_decimal(valor_passagens) or Decimal("0")
            v_devolucao = converter_decimal(valor_devolucao) or Decimal("0")
            v_outros = converter_decimal(valor_outros_gastos) or Decimal("0")
            valor_total = v_diarias + v_passagens + v_outros - v_devolucao

            linhas.append((
                id_viagem,
                limpar_texto(num_proposta, 20),
                limpar_texto(situacao, 50),
                limpar_texto(viagem_urgente, 5),
                limpar_texto(cod_orgao_superior, 20),
                nome_orgao_superior,
                limpar_texto(nome_viajante, 255),
                limpar_texto(cargo, 255),
                d_inicio,
                d_fim,
                limpar_texto(destinos, 4000),
                limpar_texto(motivo, 4000),
                v_diarias, v_passagens, v_devolucao, v_outros,
                valor_total, duracao_dias,
            ))
            ids_validos.add(id_viagem)

        if linhas:
            banco.inserir_em_lote(conexao_escrita, sql_insert, linhas)
            total_inseridas += len(linhas)
            print(f"[transformar]   +{len(linhas)} viagens (total {total_inseridas})")

    print(f"[transformar] silver_viagem concluída: {total_inseridas} linhas.\n")
    return ids_validos


# ---------------------------------------------------------------------------
# silver_pagamento
# ---------------------------------------------------------------------------
def transformar_pagamento(conexao_leitura, conexao_escrita, ids_validos: set) -> None:
    print("[transformar] silver_pagamento...")
    banco.executar(conexao_escrita, "TRUNCATE TABLE silver_pagamento;")

    colunas_raw = [
        "id_viagem", "num_proposta", "nome_orgao_pagador",
        "nome_ug_pagadora", "tipo_pagamento", "valor",
    ]
    sql_insert = """
        INSERT INTO silver_pagamento (
            id_viagem, num_proposta, nome_orgao_pagador, nome_ug_pagadora,
            tipo_pagamento, valor
        ) VALUES (%s, %s, %s, %s, %s, %s);
    """

    total = 0
    for bloco in ler_raw_em_blocos(conexao_leitura, "raw_pagamento", colunas_raw):
        linhas = []
        for row in bloco:
            id_viagem, num_proposta, nome_orgao_pagador, nome_ug_pagadora, tipo_pagamento, valor = row
            id_viagem = limpar_texto(id_viagem, 20)
            tipo_pagamento = limpar_texto(tipo_pagamento, 50)

            if not id_viagem or id_viagem not in ids_validos:
                continue
            if not tipo_pagamento:  # NOT NULL
                continue

            linhas.append((
                id_viagem,
                limpar_texto(num_proposta, 20),
                limpar_texto(nome_orgao_pagador, 255),
                limpar_texto(nome_ug_pagadora, 255),
                tipo_pagamento,
                converter_decimal(valor) or Decimal("0"),
            ))

        if linhas:
            banco.inserir_em_lote(conexao_escrita, sql_insert, linhas)
            total += len(linhas)
            print(f"[transformar]   +{len(linhas)} pagamentos (total {total})")

    print(f"[transformar] silver_pagamento concluída: {total} linhas.\n")


# ---------------------------------------------------------------------------
# silver_passagem
# ---------------------------------------------------------------------------
def transformar_passagem(conexao_leitura, conexao_escrita, ids_validos: set) -> None:
    print("[transformar] silver_passagem...")
    banco.executar(conexao_escrita, "TRUNCATE TABLE silver_passagem;")

    colunas_raw = [
        "id_viagem", "meio_transporte", "pais_origem_ida", "uf_origem_ida",
        "cidade_origem_ida", "pais_destino_ida", "uf_destino_ida",
        "cidade_destino_ida", "valor_passagem", "taxa_servico", "data_emissao",
    ]
    sql_insert = """
        INSERT INTO silver_passagem (
            id_viagem, meio_transporte, pais_origem_ida, uf_origem_ida,
            cidade_origem_ida, pais_destino_ida, uf_destino_ida, cidade_destino_ida,
            valor_passagem, taxa_servico, data_emissao
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
    """

    total = 0
    for bloco in ler_raw_em_blocos(conexao_leitura, "raw_passagem", colunas_raw):
        linhas = []
        for row in bloco:
            (id_viagem, meio_transporte, pais_origem_ida, uf_origem_ida,
             cidade_origem_ida, pais_destino_ida, uf_destino_ida,
             cidade_destino_ida, valor_passagem, taxa_servico, data_emissao) = row

            id_viagem = limpar_texto(id_viagem, 20)
            if not id_viagem or id_viagem not in ids_validos:
                continue

            v_passagem = converter_decimal(valor_passagem)
            t_servico = converter_decimal(taxa_servico)
            if v_passagem is not None and v_passagem < 0:
                continue
            if t_servico is not None and t_servico < 0:
                continue

            linhas.append((
                id_viagem,
                limpar_texto(meio_transporte, 50),
                limpar_texto(pais_origem_ida, 60),
                limpar_texto(uf_origem_ida, 40),
                limpar_texto(cidade_origem_ida, 80),
                limpar_texto(pais_destino_ida, 60),
                limpar_texto(uf_destino_ida, 40),
                limpar_texto(cidade_destino_ida, 80),
                v_passagem or Decimal("0"),
                t_servico or Decimal("0"),
                converter_data(data_emissao),
            ))

        if linhas:
            banco.inserir_em_lote(conexao_escrita, sql_insert, linhas)
            total += len(linhas)
            print(f"[transformar]   +{len(linhas)} passagens (total {total})")

    print(f"[transformar] silver_passagem concluída: {total} linhas.\n")


# ---------------------------------------------------------------------------
# silver_trecho
# ---------------------------------------------------------------------------
def transformar_trecho(conexao_leitura, conexao_escrita, ids_validos: set) -> None:
    print("[transformar] silver_trecho...")
    banco.executar(conexao_escrita, "TRUNCATE TABLE silver_trecho;")

    colunas_raw = [
        "id_viagem", "sequencia_trecho", "origem_data", "origem_uf", "origem_cidade",
        "destino_data", "destino_uf", "destino_cidade", "meio_transporte", "numero_diarias",
    ]
    sql_insert = """
        INSERT INTO silver_trecho (
            id_viagem, sequencia_trecho, origem_data, origem_uf, origem_cidade,
            destino_data, destino_uf, destino_cidade, meio_transporte, numero_diarias
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id_viagem, sequencia_trecho) DO NOTHING;
    """

    total = 0
    for bloco in ler_raw_em_blocos(conexao_leitura, "raw_trecho", colunas_raw):
        linhas = []
        for row in bloco:
            (id_viagem, sequencia_trecho, origem_data, origem_uf, origem_cidade,
             destino_data, destino_uf, destino_cidade, meio_transporte, numero_diarias) = row

            id_viagem = limpar_texto(id_viagem, 20)
            if not id_viagem or id_viagem not in ids_validos:
                continue

            seq = converter_inteiro(sequencia_trecho)
            if seq is None:
                continue

            n_diarias = converter_decimal(numero_diarias)
            if n_diarias is not None and n_diarias < 0:
                continue

            linhas.append((
                id_viagem,
                seq,
                converter_data(origem_data),
                limpar_texto(origem_uf, 40),
                limpar_texto(origem_cidade, 80),
                converter_data(destino_data),
                limpar_texto(destino_uf, 40),
                limpar_texto(destino_cidade, 80),
                limpar_texto(meio_transporte, 50),
                n_diarias or Decimal("0"),
            ))

        if linhas:
            banco.inserir_em_lote(conexao_escrita, sql_insert, linhas)
            total += len(linhas)
            print(f"[transformar]   +{len(linhas)} trechos (total {total})")

    print(f"[transformar] silver_trecho concluída: {total} linhas.\n")


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------
def main() -> None:
    # Usamos DUAS conexões separadas:
    #   - conexao_leitura: só faz SELECT nas tabelas raw, com cursor nomeado
    #     (server-side), para não carregar os CSVs inteiros na memória.
    #   - conexao_escrita: faz TRUNCATE/INSERT/commit na Silver.
    # Isso evita o erro "named cursor isn't valid anymore", que acontece
    # quando um commit na mesma conexão do cursor nomeado invalida o cursor.
    try:
        conexao_leitura = banco.conectar()
        conexao_escrita = banco.conectar()
    except RuntimeError as erro:
        print(f"[transformar] ERRO ao conectar no banco: {erro}")
        sys.exit(1)

    # cursores nomeados (server-side) exigem que a conexão NÃO esteja em
    # autocommit e sejam usados dentro de uma transação
    conexao_leitura.autocommit = False

    try:
        ids_validos = transformar_viagem(conexao_leitura, conexao_escrita)
        transformar_pagamento(conexao_leitura, conexao_escrita, ids_validos)
        transformar_passagem(conexao_leitura, conexao_escrita, ids_validos)
        transformar_trecho(conexao_leitura, conexao_escrita, ids_validos)

        print("[transformar] Pipeline Raw -> Silver concluído com sucesso.")
    except Exception as erro:
        conexao_escrita.rollback()
        print(f"[transformar] ERRO durante a transformação, rollback aplicado: {erro}")
        sys.exit(1)
    finally:
        conexao_leitura.close()
        conexao_escrita.close()
        print("[transformar] Conexões encerradas.")


if __name__ == "__main__":
    main()