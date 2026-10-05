from pathlib import Path
import csv
import json
from openpyxl import load_workbook,workbook

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


def read_excel(path: Path) -> dict[str,list[dict]]:
    wb = load_workbook(path,read_only=True,data_only=True)

    data = {}

    for sheet in wb.worksheets:
            rows = sheet.iter_rows(values_only=True)

            try:
                headers = next(rows)
            except StopIteration:
                data[sheet.title] = []
                continue

            data[sheet.title] = [
                dict(zip(headers, row))
                for row in rows
            ]

    wb.close()

    return data

@tool
def create_json(name:str,ext:str)->str:

    """
      Lê uma planilha suportada e retorna seu contéudo em formato JSON

      Args:
         name: nome do arquivo sem extensão, por exemplo academia.
         ext: extensão do arquivo, por exemplo csv ou xlsx.
    """

    path = BASE_DIR / "../../../sheets/" / ext / (name + "." + ext)

    if ext == "csv":
        dados = read_csv(path)
    elif ext == "xlsx":
        dados = read_excel(path)
    else:
        raise ValueError("Extensão não suportada")

    json_dados = json.dumps(
        dados,
        ensure_ascii=False,
        indent=2,
        default=str
    )

    return json_dados

if __name__ == "__main__":
    print(create_json("academia","csv"))
