from pathlib import Path
import csv
import json

from langchain_core.tools import tool

BASE_DIR = Path(__file__).resolve().parent

def read_csv(path: Path)-> list[dict]:
    encodings = ["utf-8-sig","utf-8","cp1252","latin-1"]

    for encoding in encodings:
        try:
            with path.open("r", encoding=encoding) as arquivo:
                return list(csv.DictReader(arquivo))
        except UnicodeDecodeError:
            continue

    raise ValueError("Não foi possível ler o arquivo")


@tool
def create_json(name:str,ext:str)->str:

    """
       Lê uma planilha suportada e retorna seu contéudo em formato JSON

      Args:
         name: nome do arquivo sem extensão, por exemplo academia.
         ext: extensão do arquivo, por exemplo csv.
    """

    path = BASE_DIR / "../../../sheets/" / ext / (name + "." + ext)

    dados = read_csv(path)

    json_dados = json.dumps(
        dados,
        ensure_ascii=False,
        indent=2
    )
    return json_dados

if __name__ == "__main__":
    print(create_json("academia","csv"))
