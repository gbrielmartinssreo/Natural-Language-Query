import json
from pathlib import Path

from langchain_core.tools import tool

from nlq.data.semantic_search import search_documents
from nlq.paths import data_dir


from time import perf_counter

# Orçamento de caracteres da resposta da ferramenta. Resultados muito
# extensos inflam o contexto do modelo e aumentam a latência.
LIMITE_CARACTERES = 6000

# Limite de caracteres por registro, para não estourar o orçamento
# com um único documento longo.
LIMITE_POR_REGISTRO = 1500


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

    Use quando a identificação depender de significado, sinônimos ou
    interpretação conceitual, mesmo quando as palavras da pergunta forem
    diferentes das presentes na planilha. Não use quando os critérios
    puderem ser verificados diretamente nos valores das colunas: nesse
    caso, prefira consultar_dados.

    Evite extrair a planilha inteira para responder uma busca pontual.
    Não garante cobertura completa nem um resumo representativo do arquivo.

    Não use esta ferramenta para contagens, somas, cálculos exatos nem
    para filtros textuais por correspondência direta dos valores. Para
    essas operações, use consultar_dados.

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

        # Ajusta em vez de falhar: o modelo pode pedir um top_k fora
        # da faixa e isso não deve interromper a consulta.
        top_k = max(1, min(int(top_k), 20))

        path = _resolve_path(name, ext)
        results = search_documents(path, query, top_k=top_k)

        if not results:
            resultado = "Nenhum registro relevante encontrado."
            status = "ok"
            return resultado

        lines = []
        total = 0
        omitidos = 0

        for index, (document, score) in enumerate(results, start=1):
            sheet = document.metadata.get("sheet")
            location = f" | Aba: {sheet}" if sheet else ""

            registro = document.metadata.get("record_index")
            ref = {"aba": sheet or "", "indice": registro}

            conteudo = document.page_content

            if len(conteudo) > LIMITE_POR_REGISTRO:
                conteudo = (
                    conteudo[:LIMITE_POR_REGISTRO]
                    + "\n[...]"
                )

            bloco = (
                f"Resultado {index} | Similaridade: {score:.4f}{location}"
                f" | Registro: {registro}\n"
                f"Ref para consultar_dados: "
                f"{json.dumps(ref, ensure_ascii=False, separators=(',', ':'))}\n"
                f"{conteudo}"
            )

            # Sempre inclui o primeiro resultado; os demais respeitam
            # o orçamento total de caracteres.
            if lines and total + len(bloco) > LIMITE_CARACTERES:
                omitidos = len(results) - index + 1
                break

            lines.append(bloco)
            total += len(bloco) + len("\n\n---\n\n")

        if omitidos:
            lines.append(
                f"[{omitidos} resultado(s) omitido(s) por limite de "
                f"tamanho. Refine a busca ou use consultar_dados para "
                f"dados exatos.]"
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
