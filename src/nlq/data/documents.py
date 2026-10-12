"""Transforma registros de planilhas em documentos para busca semântica."""

from pathlib import Path

from langchain_core.documents import Document

from .loader import load_records


def _format_value(value: object) -> str:
    """Converte um valor da planilha em texto."""
    if value is None:
        return ""

    return str(value).strip()


def _record_to_text(record: dict) -> str:
    """Transforma os campos de um registro em texto pesquisável."""
    fields = []

    for name, value in record.items():
        text = _format_value(value)

        if not text:
            continue

        fields.append(f"{name}: {text}")

    return "\n".join(fields)


def build_documents(path: str | Path) -> list[Document]:
    """Cria um documento por registro da planilha."""
    path = Path(path).resolve()
    records = load_records(path)
    documents = []

    if isinstance(records, dict):
        # XLSX: cada aba contém uma lista de registros.
        sheets = records.items()
    else:
        # CSV: não possui abas.
        sheets = [(None, records)]

    for sheet_name, rows in sheets:
        for index, record in enumerate(rows, start=1):
            content = _record_to_text(record)

            if not content:
                continue

            metadata = {
                "source": path.name,
                "record_index": index,
            }

            if sheet_name is not None:
                metadata["sheet"] = sheet_name

            documents.append(
                Document(
                    page_content=content,
                    metadata=metadata,
                )
            )

    return documents
