from pathlib import Path
import json

from langchain_core.tools import tool

from nlq.data.loader import load_records, read_csv, read_workbook
from nlq.data.schema import build_schema, make_headers as _make_headers

__all__ = ["create_json", "read_csv", "read_excel"]


BASE_DIR = Path(__file__).resolve().parent


def read_excel(path: Path) -> dict[str, list[dict]]:
    """Lê um XLSX sem cache. Mantido por compatibilidade."""
    path = Path(path)
    return read_workbook(path, build_schema(path))


@tool
def create_json(name: str, ext: str) -> str:
    """
    Lê uma planilha suportada e retorna seu conteúdo em JSON.

    Args:
        name: Nome do arquivo sem extensão, por exemplo academia.
        ext: Extensão do arquivo, por exemplo csv ou xlsx.
    """
    ext = ext.lower().lstrip(".")

    if ext not in ("csv", "xlsx"):
        raise ValueError("Extensão não suportada")

    path = (BASE_DIR / "../../../sheets" / ext / f"{name}.{ext}").resolve()

    if not path.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    dados = load_records(path)

    return json.dumps(
        dados,
        ensure_ascii=False,
        indent=2,
        default=str,
    )


if __name__ == "__main__":
    print(create_json("matriz", "xlsx"))
