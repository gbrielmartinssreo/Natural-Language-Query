from pathlib import Path
import csv
import json

from langchain_core.tools import tool

BASE_DIR = Path(__file__).resolve().parent

@tool
def create_json(name:str,ext:str)->str:

    """
       Lê uma planilha suportada e retorna seu contéudo em formato JSON

      Args:
         name: nome do arquivo sem extensão, por exemplo academia.
         ext: extensão do arquivo, por exemplo csv.
    """

    path = BASE_DIR / "../../../sheets/" / ext / (name + "." + ext)

    with path.open("r", encoding="utf-8") as arquivo:
        dados = list(csv.DictReader(arquivo))

    json_dados = json.dumps(
        dados,
        ensure_ascii=False,
        indent=2
    )
    return json_dados

if __name__ == "__main__":
    print(create_json("academia","csv"))
