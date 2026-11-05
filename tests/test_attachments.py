"""Ciclo de vida e isolamento dos anexos por conversa."""

import io
import tempfile
import uuid
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

import nlq.attachments as attachments
from nlq.data.semantic_search import _INDEX_CACHE, _cache_file, evict_index


@pytest.fixture()
def upload_root():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        with mock.patch.dict("os.environ", {"NLQ_UPLOAD_ROOT": directory}):
            yield Path(directory)


def _thread() -> str:
    return str(uuid.uuid4())


def _csv(content: bytes = b"nome,valor\na,1\n") -> io.BytesIO:
    return io.BytesIO(content)


def test_anexo_so_e_visivel_na_propria_conversa(upload_root):
    owner = _thread()
    other = _thread()
    attachment = attachments.add_attachment(owner, "dados.csv", _csv())

    with attachments.conversation_scope(owner):
        assert "dados.csv" in attachments.list_visible_files("csv")
        assert attachments.resolve_visible_path("dados", "csv").is_file()

    with attachments.conversation_scope(other):
        assert "dados.csv" not in attachments.list_visible_files("csv")
        with pytest.raises(FileNotFoundError):
            attachments.resolve_visible_path("dados", "csv")

    assert attachment["nome"] == "dados"


def test_nome_duplicado_recebe_sufixo(upload_root):
    thread_id = _thread()
    first = attachments.add_attachment(thread_id, "dados.csv", _csv())
    second = attachments.add_attachment(thread_id, "dados.csv", _csv())

    assert first["nome"] == "dados"
    assert second["nome"] == "dados-2"


def test_remocao_individual(upload_root):
    thread_id = _thread()
    item = attachments.add_attachment(thread_id, "dados.csv", _csv())

    assert attachments.delete_attachment(thread_id, item["id"])
    assert attachments.list_attachments(thread_id) == []
    assert not attachments.delete_attachment(thread_id, item["id"])


def test_remocao_apaga_indice_em_disco_sem_cache_em_ram(upload_root):
    thread_id = _thread()
    item = attachments.add_attachment(thread_id, "dados.csv", _csv())
    path = Path(
        attachments._read_metadata(thread_id)["attachments"][0]["path"]
    ).resolve()
    stat = path.stat()
    fingerprint = (stat.st_mtime_ns, stat.st_size)
    cache_file = _cache_file(path, fingerprint)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(b"cache")
    _INDEX_CACHE.pop(path.resolve(), None)

    evict_index(path)

    assert not cache_file.exists()


def test_mensagem_renova_prazo(upload_root):
    thread_id = _thread()
    item = attachments.add_attachment(thread_id, "dados.csv", _csv())
    uploaded = item["enviado_em"]
    attachments.touch_message(thread_id, now=uploaded + 100)

    assert not attachments.expire_thread(
        thread_id, now=uploaded + attachments.TTL_SECONDS + 50
    )
    assert attachments.expire_thread(
        thread_id, now=uploaded + attachments.TTL_SECONDS + 101
    )


def test_upload_nao_renova_prazo_de_conversa_com_mensagem(upload_root):
    thread_id = _thread()
    first = attachments.add_attachment(thread_id, "a.csv", _csv())
    message_at = first["enviado_em"] + 10
    attachments.touch_message(thread_id, now=message_at)

    with mock.patch("nlq.attachments.time.time", return_value=message_at + 100):
        attachments.add_attachment(thread_id, "b.csv", _csv())

    assert attachments.expire_thread(
        thread_id, now=message_at + attachments.TTL_SECONDS
    )
    assert attachments.list_attachments(thread_id) == []


def test_limites_de_quantidade_e_tamanho(upload_root):
    thread_id = _thread()
    with mock.patch.object(attachments, "MAX_FILES_PER_THREAD", 1):
        attachments.add_attachment(thread_id, "a.csv", _csv())
        with pytest.raises(ValueError, match="Limite de 1"):
            attachments.add_attachment(thread_id, "b.csv", _csv())

    other = _thread()
    with mock.patch.object(attachments, "MAX_FILE_BYTES", 4):
        with pytest.raises(ValueError, match="excede o limite"):
            attachments.add_attachment(other, "grande.csv", _csv(b"12345"))


def test_endpoints_de_upload_listagem_e_remocao(upload_root):
    import nlq.api as api

    thread_id = _thread()
    with TestClient(api.app) as client:
        response = client.post(
            "/api/anexos",
            data={"thread_id": thread_id},
            files={"file": ("dados.csv", b"nome,valor\na,1\n", "text/csv")},
        )
        assert response.status_code == 201
        attachment = response.json()["anexo"]

        response = client.get("/api/anexos", params={"thread_id": thread_id})
        assert response.json()["anexos"] == [attachment]

        response = client.delete(
            f"/api/anexos/{attachment['id']}", params={"thread_id": thread_id}
        )
        assert response.status_code == 200
        assert attachments.list_attachments(thread_id) == []


@pytest.mark.parametrize("filename", ["dados.txt", "../dados.csv", ""])
def test_rejeita_nome_ou_formato_invalido(upload_root, filename):
    with pytest.raises(ValueError):
        attachments.add_attachment(_thread(), filename, _csv())


def test_rejeita_xlsx_com_conteudo_invalido(upload_root):
    with pytest.raises(ValueError, match="XLSX inválido"):
        attachments.add_attachment(_thread(), "dados.xlsx", io.BytesIO(b"not-xlsx"))
