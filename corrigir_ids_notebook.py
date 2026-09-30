"""
corrigir_ids_notebook.py
-------------------------
Corrige o erro "Invalid Notebook" no GitHub SEM apagar as saídas (tabelas e
gráficos) que você já gerou ao rodar o notebook.

O que faz: abre o .ipynb, adiciona um campo "id" único em cada célula que
ainda não tiver (exigido pelo formato nbformat 4.5), e salva de volta —
mantendo 100% do conteúdo, código e saídas que já existiam.

COMO USAR:
    python corrigir_ids_notebook.py 3_analise.ipynb
"""

import json
import sys
import uuid


def corrigir(caminho: str) -> None:
    with open(caminho, encoding="utf-8") as f:
        nb = json.load(f)

    corrigidas = 0
    for cell in nb["cells"]:
        if "id" not in cell:
            cell["id"] = uuid.uuid4().hex[:8]
            corrigidas += 1

    nb["nbformat_minor"] = max(nb.get("nbformat_minor", 5), 5)

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)

    print(f"{caminho}: {corrigidas} célula(s) receberam id novo. "
          f"Saídas e código permanecem intactos.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python corrigir_ids_notebook.py NOME_DO_ARQUIVO.ipynb")
        sys.exit(1)
    corrigir(sys.argv[1])
