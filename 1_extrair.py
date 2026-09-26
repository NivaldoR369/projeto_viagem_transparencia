"""
1_extrair.py
------------
Fase 1 do pipeline - Extração e camada Raw.

O que este script faz:
    1) Baixa o .zip com os 4 CSVs de Viagens a Serviço direto do Google Drive
       (usando o DRIVE_FILE_ID configurado em config.py), sem intervenção manual.
    2) Extrai o .zip na pasta data/.
    3) Lê cada CSV em blocos (chunks) de TAMANHO_BLOCO linhas, sem alterar
       nenhum valor (tudo entra como texto, exatamente como está no arquivo).
    4) Carrega cada bloco na tabela RAW correspondente.

Idempotência: antes de carregar, cada tabela RAW é truncada (TRUNCATE), então
rodar o script várias vezes nunca duplica registros.

Resiliência: cada etapa (download, extração, leitura, carga por tabela) está
protegida por try/except, com mensagens claras sobre o que falhou.
"""

import sys
import zipfile
from pathlib import Path

import pandas as pd

import banco
from config import (
    ARQUIVOS,
    CSV_ENCODING,
    CSV_SEPARADOR,
    DRIVE_FILE_ID,
    PASTA_DADOS,
    TAMANHO_BLOCO,
)

NOME_ZIP = "viagens.zip"


# ---------------------------------------------------------------------------
# Etapa 1: download do .zip no Google Drive
# ---------------------------------------------------------------------------
def baixar_zip_do_drive() -> Path:
    """
    Baixa o .zip configurado (DRIVE_FILE_ID) do Google Drive para dentro de
    PASTA_DADOS. Se o arquivo já existir localmente, reaproveita (não baixa
    de novo), o que é útil em reexecuções.
    """
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    caminho_zip = PASTA_DADOS / NOME_ZIP

    if caminho_zip.exists():
        print(f"[extrair] Zip já existe em {caminho_zip}, pulando download.")
        return caminho_zip

    if not DRIVE_FILE_ID or DRIVE_FILE_ID == "COLE_AQUI_O_ID_DO_ARQUIVO_NO_DRIVE":
        raise RuntimeError(
            "DRIVE_FILE_ID não configurado em config.py. Abra o arquivo no "
            "Google Drive, clique em 'Compartilhar' -> 'Qualquer pessoa com "
            "o link' e copie o ID que fica em .../file/d/ESTE_TRECHO/view."
        )

    try:
        import gdown
    except ImportError as erro:
        raise RuntimeError(
            "A biblioteca 'gdown' não está instalada. Rode: pip install gdown"
        ) from erro

    print(f"[extrair] Baixando zip do Google Drive (id={DRIVE_FILE_ID})...")
    try:
        gdown.download(
            id=DRIVE_FILE_ID,
            output=str(caminho_zip),
            quiet=False,
        )
    except Exception as erro:
        raise RuntimeError(f"Falha ao baixar o arquivo do Google Drive: {erro}") from erro

    if not caminho_zip.exists():
        raise RuntimeError("Download concluído mas o arquivo .zip não foi encontrado.")

    print(f"[extrair] Download concluído: {caminho_zip}")
    return caminho_zip


# ---------------------------------------------------------------------------
# Etapa 2: extração do .zip
# ---------------------------------------------------------------------------
def extrair_zip(caminho_zip: Path) -> None:
    """Extrai todos os CSVs do .zip para dentro de PASTA_DADOS."""
    try:
        with zipfile.ZipFile(caminho_zip, "r") as zip_ref:
            zip_ref.extractall(PASTA_DADOS)
        print(f"[extrair] Zip extraído em {PASTA_DADOS}")
    except zipfile.BadZipFile as erro:
        raise RuntimeError(f"O arquivo baixado não é um .zip válido: {erro}") from erro


# ---------------------------------------------------------------------------
# Etapa 3: truncar tabela raw (garante idempotência)
# ---------------------------------------------------------------------------
def truncar_tabela(conexao, tabela: str) -> None:
    print(f"[extrair] Truncando {tabela}...")
    banco.executar(conexao, f"TRUNCATE TABLE {tabela};")


# ---------------------------------------------------------------------------
# Etapa 4: ler o CSV em blocos e carregar na tabela raw
# ---------------------------------------------------------------------------
def carregar_csv_em_blocos(conexao, caminho_csv: Path, tabela: str) -> int:
    """
    Lê caminho_csv em blocos de TAMANHO_BLOCO linhas (sem converter nenhum
    valor - tudo como string) e insere cada bloco na tabela raw informada.
    Retorna o total de linhas carregadas.
    """
    total_linhas = 0

    leitor = pd.read_csv(
        caminho_csv,
        sep=CSV_SEPARADOR,
        encoding=CSV_ENCODING,
        dtype=str,
        keep_default_na=False,
        chunksize=TAMANHO_BLOCO,
    )

    for numero_bloco, bloco in enumerate(leitor, start=1):
        colunas = ", ".join(f"col{i}" for i in range(len(bloco.columns)))
        # descobre os nomes reais das colunas da tabela raw (na mesma ordem
        # do CREATE TABLE) consultando o information_schema uma única vez
        placeholders = ", ".join(["%s"] * len(bloco.columns))
        sql_insert = f"INSERT INTO {tabela} VALUES ({placeholders})"

        linhas = [tuple(linha) for linha in bloco.itertuples(index=False, name=None)]
        banco.inserir_em_lote(conexao, sql_insert, linhas)

        total_linhas += len(linhas)
        print(f"[extrair]   bloco {numero_bloco} de {tabela}: +{len(linhas)} linhas "
              f"(total {total_linhas})")

    return total_linhas


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------
def main() -> None:
    try:
        caminho_zip = baixar_zip_do_drive()
        extrair_zip(caminho_zip)
    except RuntimeError as erro:
        print(f"[extrair] ERRO na etapa de download/extração: {erro}")
        sys.exit(1)

    try:
        conexao = banco.conectar()
    except RuntimeError as erro:
        print(f"[extrair] ERRO ao conectar no banco: {erro}")
        sys.exit(1)

    try:
        for chave, info in ARQUIVOS.items():
            caminho_csv = PASTA_DADOS / info["csv"]
            tabela = info["tabela_raw"]

            if not caminho_csv.exists():
                print(f"[extrair] AVISO: {caminho_csv} não encontrado, pulando {tabela}.")
                continue

            try:
                truncar_tabela(conexao, tabela)
                total = carregar_csv_em_blocos(conexao, caminho_csv, tabela)
                print(f"[extrair] OK: {total} linhas carregadas em {tabela}.\n")
            except Exception as erro:
                print(f"[extrair] ERRO ao carregar {tabela}: {erro}")
                conexao.rollback()
                continue
    finally:
        conexao.close()
        print("[extrair] Conexão encerrada.")


if __name__ == "__main__":
    main()
