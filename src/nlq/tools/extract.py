from pathlib import Path
import json

from langchain_core.tools import tool

from nlq.data.loader import load_records, read_csv, read_workbook
from nlq.data.schema import build_schema, make_headers as _make_headers
from nlq.paths import data_dir

from time import perf_counter

__all__ = ["create_json", "read_csv", "read_excel"]


def read_excel(path: Path) -> dict[str, list[dict]]:
    """Lê um XLSX sem cache. Mantido por compatibilidade."""
    path = Path(path)
    return read_workbook(path, build_schema(path))


@tool
def create_json(name: str, ext: str) -> str:
    """
    Extrai TODOS os registros de uma planilha e retorna seu conteúdo em JSON.

    Use somente quando for necessária uma extração ampla ou completa.
    Para filtros, contagens e operações sobre os valores, use consultar_dados.
    Para localizar conteúdo por significado, use buscar_semantico.
    Para nomes de abas e colunas, use consultar_schema.
    Não use por padrão para perguntas gerais ou buscas pontuais.

    Args:
        name: Nome do arquivo sem extensão, por exemplo academia.
        ext: Extensão do arquivo, por exemplo csv ou xlsx.
    """

    inicio = perf_counter()
    resultado = None
    status = "erro"
    print("[TOOL] create_json inicio", flush=True)
    try:
        ext = ext.lower().lstrip(".")

        if ext not in ("csv", "xlsx"):
            raise ValueError("Extensão não suportada")

        path = (data_dir() / ext / f"{name}.{ext}").resolve()

        if not path.is_file():
            raise FileNotFoundError(f"Arquivo não encontrado: {path}")

        dados = load_records(path)

        resultado = json.dumps(
                dados,
                ensure_ascii=False,
                indent=2,
                default=str,
            )

        limite_caracteres = 20_000
        tamanho = len(resultado)

        if tamanho > limite_caracteres:
                resultado = (
                    "EXTRACAO_BLOQUEADA_POR_TAMANHO\n"
                    f"O conteúdo completo possui {tamanho} caracteres, "
                    f"acima do limite de {limite_caracteres}.\n"
                    "Os registros não foram enviados.\n"
                    "Use buscar_semantico para perguntas sobre conteúdo. "
                    "Não repita create_json para este arquivo nesta consulta. "
                    "Para cálculos completos, use uma consulta estruturada; "
                    "se não estiver disponível, informe a limitação."
                )

        status = "ok"
        return resultado
    finally:
        duracao = perf_counter() - inicio
        caracteres = len(resultado) if resultado is not None else 0
        print(
            f"[PERF] tool=create_json status={status} "
            f"tempo={duracao:.4f}s caracteres={caracteres}",
            flush=True,
        )


if __name__ == "__main__":
    print(create_json.invoke({"name": "matriz", "ext": "xlsx"}))
