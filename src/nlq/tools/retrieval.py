from pathlib import Path

from langchain_core.tools import tool

from nlq.data.semantic_search import search_documents
from nlq.paths import data_dir


from time import perf_counter


def _resolve_path(name: str, ext: str) -> Path:
    sheets_dir = data_dir().resolve()
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

    Prefira esta ferramenta para perguntas sobre assuntos, iniciativas,
    medidas, problemas, objetivos ou metas específicos presentes no arquivo.
    Evite extrair a planilha inteira para responder uma busca pontual.
    Não garante cobertura completa nem um resumo representativo do arquivo.

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

    inicio = perf_counter()
    resultado = None
    status = "erro"
    print("[TOOL] buscar_semantico inicio", flush=True)
    try:
        ext = ext.lower().lstrip(".")

        if ext not in ("csv", "xlsx"):
            raise ValueError("Extensão não suportada")

        if top_k < 1 or top_k > 20:
            raise ValueError("top_k deve estar entre 1 e 20")

        path = _resolve_path(name, ext)
        results = search_documents(path, query, top_k=top_k)

        if not results:
            resultado = "Nenhum registro relevante encontrado."
            status = "ok"
            return resultado

        lines = []

        for index, (document, score) in enumerate(results, start=1):
            sheet = document.metadata.get("sheet")
            location = f" | Aba: {sheet}" if sheet else ""

            lines.append(
                f"Resultado {index} | Similaridade: {score:.4f}{location}\n"
                f"{document.page_content}"
            )


        resultado = "\n\n---\n\n".join(lines)
        status = "ok"
        return resultado
    finally:
        duracao = perf_counter() - inicio
        caracteres = len(resultado) if resultado is not None else 0
        print(
            f"[PERF] tool=buscar_semantico status={status} "
            f"tempo={duracao:.4f}s caracteres={caracteres}",
            flush=True,
        )
