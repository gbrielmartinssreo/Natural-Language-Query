from langchain_core.tools import tool

from nlq.attachments import list_visible_files


def listar_csvs() -> list[str]:
    return list_visible_files("csv")


def listar_xlsx() -> list[str]:
    return list_visible_files("xlsx")


@tool
def lista_arquivos() -> list[str]:
    """
    Lista todos os arquivos CSV e XLSX na pasta de planilhas.
    """
    return listar_csvs() + listar_xlsx()


if __name__ == "__main__":
    print(lista_arquivos())
