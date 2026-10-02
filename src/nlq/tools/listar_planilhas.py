from langchain_core.tools import tool

from pathlib import Path
import re

BASE_DIR = Path(__file__).resolve().parent


def listar_csvs() -> list[str]:
    docs_dir = (BASE_DIR / "../../../sheets/csv").resolve()

    archives = []

    for item in docs_dir.iterdir():
        if item.is_file():
            nome = re.sub(r"\([^)]*\)", "", item.name)
            archives.append(nome.strip())

    return archives


def listar_xlsx() -> list[str]:
    docs_dir = (BASE_DIR / "../../../sheets/xlsx").resolve()

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
