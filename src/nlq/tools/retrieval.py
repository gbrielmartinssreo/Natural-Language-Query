from pathlib import Path

from langchain_core.tools import tool

from nlq.data.semantic_search import search_documents


BASE_DIR = Path(__file__).resolve().parent


def _resolve_path(name: str, ext: str) -> Path:
    sheets_dir = (BASE_DIR / "../../../sheets").resolve()
    path = (sheets_dir / ext / f"{name}.{ext}").resolve()

    if not path.is_relative_to(sheets_dir):
        raise ValueError("Nome de arquivo inválido")

    if not path.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    return path


@tool
def buscar_semantico(
    name: str,
    ext: str,
    query: str,
    top_k: int = 5,
) -> str:
    """
    Busca registros semanticamente relacionados a uma pergunta.

    Use para encontrar indicadores, medidas, problemas e metas
    relacionados ao significado da pergunta, mesmo quando as palavras
    utilizadas forem diferentes das presentes na planilha.

    Não use esta ferramenta para contagens, somas ou cálculos exatos.
    Para essas operações, consulte os dados estruturados.

    Args:
        name: Nome do arquivo sem extensão, por exemplo matriz.
        ext: Extensão do arquivo: csv ou xlsx.
        query: Pergunta ou conceito que será pesquisado.
        top_k: Quantidade máxima de registros relevantes a retornar.
    """
    ext = ext.lower().lstrip(".")

    if ext not in ("csv", "xlsx"):
        raise ValueError("Extensão não suportada")

    if top_k < 1 or top_k > 20:
        raise ValueError("top_k deve estar entre 1 e 20")

    path = _resolve_path(name, ext)
    results = search_documents(path, query, top_k=top_k)

    if not results:
        return "Nenhum registro relevante encontrado."

    lines = []

    for index, (document, score) in enumerate(results, start=1):
        sheet = document.metadata.get("sheet")
        location = f" | Aba: {sheet}" if sheet else ""

        lines.append(
            f"Resultado {index} | Similaridade: {score:.4f}{location}\n"
            f"{document.page_content}"
        )

    return "\n\n---\n\n".join(lines)
