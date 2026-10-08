from pathlib import Path
import csv
import json
import time
from openpyxl import load_workbook,workbook

from langchain_core.tools import tool

BASE_DIR = Path(__file__).resolve().parent

_CACHE: dict[tuple[str, float, int], str] = {}
_CACHE_MAX_ENTRIES = 8


def _perf(label: str, seconds: float | None = None) -> None:
    if seconds is None:
        print(f"[PERF] {label}", flush=True)
    else:
        print(f"[PERF] {label}: {seconds:.2f}s", flush=True)


def _cache_key(path: Path) -> tuple[str, float, int]:
    stat = path.stat()
    return (str(path.resolve()), stat.st_mtime, stat.st_size)


def _store_cache(key: tuple[str, float, int], value: str) -> None:
    path_key = key[0]

    for stale in [k for k in _CACHE if k[0] == path_key and k != key]:
        del _CACHE[stale]

    while len(_CACHE) >= _CACHE_MAX_ENTRIES:
        _CACHE.pop(next(iter(_CACHE)))

    _CACHE[key] = value


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
    t_open = time.perf_counter()
    wb = load_workbook(path,read_only=True,data_only=True)
    _perf("open workbook", time.perf_counter() - t_open)

    t_parse = time.perf_counter()
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
    _perf("parse workbook", time.perf_counter() - t_parse)

    return data

@tool
def create_json(name:str,ext:str)->str:

    """
      Lê uma planilha suportada e retorna seu contéudo em formato JSON

      Args:
         name: nome do arquivo sem extensão, por exemplo academia.
         ext: extensão do arquivo, por exemplo csv ou xlsx.
    """

    t_total = time.perf_counter()

    if ext not in ("csv", "xlsx"):
        raise ValueError("Extensão não suportada")

    path = BASE_DIR / "../../../sheets/" / ext / (name + "." + ext)

    key = _cache_key(path)

    cached = _CACHE.get(key)
    if cached is not None:
        _perf("cache hit")
        _perf("create_json total", time.perf_counter() - t_total)
        return cached

    if ext == "csv":
        t_read = time.perf_counter()
        dados = read_csv(path)
        _perf("read csv", time.perf_counter() - t_read)
    else:
        dados = read_excel(path)

    t_json = time.perf_counter()
    json_dados = json.dumps(
        dados,
        ensure_ascii=False,
        indent=2,
        default=str
    )
    _perf("to json", time.perf_counter() - t_json)

    _store_cache(key, json_dados)

    _perf("create_json total", time.perf_counter() - t_total)

    return json_dados

if __name__ == "__main__":
    print(create_json("academia","csv"))
