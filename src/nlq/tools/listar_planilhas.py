from langchain_core.tools import tool

import re

from nlq.paths import data_dir


def listar_csvs() -> list[str]:
    docs_dir = (data_dir() / "csv").resolve()

    archives = []

    for item in docs_dir.iterdir():
        if item.is_file():
            nome = re.sub(r"\([^)]*\)", "", item.name)
            archives.append(nome.strip())

    return archives


def listar_xlsx() -> list[str]:
    docs_dir = (data_dir() / "xlsx").resolve()

    archives = []

    for item in docs_dir.iterdir():
        if item.is_file():
            nome = re.sub(r"\([^)]*\)", "", item.name)
            archives.append(nome.strip())

    return archives


@tool
def lista_arquivos() -> list[str]:
    """
    Lista todos os arquivos CSV e XLSX na pasta de planilhas.
    """
    return listar_csvs() + listar_xlsx()


if __name__ == "__main__":
    print(lista_arquivos())
