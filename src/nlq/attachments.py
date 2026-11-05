"""Anexos temporários isolados por conversa."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import BinaryIO, Iterator

from openpyxl import load_workbook

from nlq.paths import data_dir


ALLOWED_EXTENSIONS = {"csv", "xlsx"}
MAX_FILE_BYTES = int(os.getenv("NLQ_UPLOAD_MAX_BYTES", str(20 * 1024 * 1024)))
MAX_FILES_PER_THREAD = int(os.getenv("NLQ_UPLOAD_MAX_FILES", "5"))
TTL_SECONDS = int(os.getenv("NLQ_UPLOAD_TTL_SECONDS", str(24 * 60 * 60)))
CHUNK_SIZE = 1024 * 1024

_CURRENT_THREAD: ContextVar[str | None] = ContextVar(
    "nlq_current_thread", default=None
)
_LOCK = threading.RLock()


def upload_root() -> Path:
    configured = os.getenv("NLQ_UPLOAD_ROOT", "").strip()
    return Path(configured) if configured else Path(tempfile.gettempdir()) / "nlq-uploads"


def validate_thread_id(thread_id: str) -> str:
    if isinstance(thread_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", thread_id):
        return thread_id
    try:
        return str(uuid.UUID(thread_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Identificador de conversa inválido") from exc


def _thread_dir(thread_id: str) -> Path:
    normalized = validate_thread_id(thread_id)
    digest = hashlib.sha256(normalized.encode()).hexdigest()
    return upload_root() / digest


def _metadata_path(thread_id: str) -> Path:
    return _thread_dir(thread_id) / "metadata.json"


def _empty_metadata() -> dict:
    return {"last_message_at": None, "revision": 0, "attachments": []}


def _read_metadata(thread_id: str) -> dict:
    path = _metadata_path(thread_id)
    if not path.is_file():
        return _empty_metadata()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data.get("attachments"), list):
            raise ValueError
        return data
    except (OSError, ValueError, json.JSONDecodeError):
        return _empty_metadata()


def _write_metadata(thread_id: str, metadata: dict) -> None:
    directory = _thread_dir(thread_id)
    directory.mkdir(parents=True, exist_ok=True)
    metadata["thread_id"] = thread_id
    path = directory / "metadata.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _public(item: dict) -> dict:
    return {
        "id": item["id"],
        "nome": item["name"],
        "ext": item["ext"],
        "tamanho": item["size"],
        "enviado_em": item["uploaded_at"],
    }


def _sanitize_filename(filename: str) -> tuple[str, str]:
    if not filename or Path(filename).name != filename:
        raise ValueError("Nome de arquivo inválido")

    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("Formato não suportado. Envie um arquivo CSV ou XLSX.")

    stem = Path(filename).stem.strip()
    stem = re.sub(r"[\x00-\x1f<>:\"/\\|?*]", "_", stem).strip(" .")
    if not stem or stem in (".", ".."):
        raise ValueError("Nome de arquivo inválido")

    return stem, suffix


def _unique_name(thread_id: str, stem: str, ext: str, metadata: dict) -> str:
    used = {
        f"{item['name']}.{item['ext']}".casefold()
        for item in metadata["attachments"]
    }
    bundled = data_dir() / ext
    if bundled.is_dir():
        used.update(item.name.casefold() for item in bundled.glob(f"*.{ext}"))

    candidate = stem
    index = 2
    while f"{candidate}.{ext}".casefold() in used:
        candidate = f"{stem}-{index}"
        index += 1
    return candidate


def _validate_csv(path: Path) -> None:
    if path.stat().st_size == 0:
        raise ValueError("O arquivo está vazio")
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with path.open("r", encoding=encoding, newline="") as stream:
                first = next(csv.reader(stream), None)
            if first is None:
                raise ValueError("O arquivo CSV está vazio")
            return
        except UnicodeDecodeError:
            continue
    raise ValueError("Não foi possível ler o arquivo CSV")


def _validate_xlsx(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            total = sum(info.file_size for info in archive.infolist())
            if total > MAX_FILE_BYTES * 10:
                raise ValueError("O conteúdo descompactado do XLSX é muito grande")
            if "[Content_Types].xml" not in archive.namelist():
                raise ValueError("Arquivo XLSX inválido")
        workbook = load_workbook(path, read_only=True, data_only=True)
        workbook.close()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Arquivo XLSX inválido") from exc


def _evict(path: Path) -> None:
    from nlq.data.loader import evict_path
    from nlq.data.semantic_search import evict_index
    from nlq.tools.consultar_dados import evict_dataframe

    evict_path(path)
    evict_dataframe(path)
    evict_index(path)


def add_attachment(thread_id: str, filename: str, source: BinaryIO) -> dict:
    thread_id = validate_thread_id(thread_id)
    stem, ext = _sanitize_filename(filename)

    with _LOCK:
        expire_thread(thread_id)
        metadata = _read_metadata(thread_id)
        if len(metadata["attachments"]) >= MAX_FILES_PER_THREAD:
            raise ValueError(
                f"Limite de {MAX_FILES_PER_THREAD} anexos por conversa atingido"
            )
        name = _unique_name(thread_id, stem, ext, metadata)
        directory = _thread_dir(thread_id) / ext
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{name}.{ext}"
        temporary = directory / f".{uuid.uuid4().hex}.upload"

        size = 0
        try:
            with temporary.open("wb") as target:
                while chunk := source.read(CHUNK_SIZE):
                    size += len(chunk)
                    if size > MAX_FILE_BYTES:
                        raise ValueError(
                            f"O arquivo excede o limite de {MAX_FILE_BYTES // (1024 * 1024)} MB"
                        )
                    target.write(chunk)

            if ext == "csv":
                _validate_csv(temporary)
            else:
                _validate_xlsx(temporary)
            os.replace(temporary, path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

        now = time.time()
        item = {
            "id": uuid.uuid4().hex,
            "name": name,
            "ext": ext,
            "size": size,
            "uploaded_at": now,
            "path": str(path),
        }
        metadata["attachments"].append(item)
        metadata["revision"] = int(metadata.get("revision", 0)) + 1
        _write_metadata(thread_id, metadata)
        return _public(item)


def _expired(metadata: dict, now: float) -> bool:
    attachments = metadata["attachments"]
    if not attachments:
        return False
    baseline = metadata.get("last_message_at")
    if baseline is None:
        baseline = max(float(item["uploaded_at"]) for item in attachments)
    return now - float(baseline) >= TTL_SECONDS


def expire_thread(thread_id: str, now: float | None = None) -> bool:
    thread_id = validate_thread_id(thread_id)
    with _LOCK:
        metadata = _read_metadata(thread_id)
        if not _expired(metadata, time.time() if now is None else now):
            return False
        delete_all(thread_id)
        return True


def sweep_expired(now: float | None = None) -> int:
    root = upload_root()
    if not root.is_dir():
        return 0
    removed = 0
    current = time.time() if now is None else now
    with _LOCK:
        for directory in root.iterdir():
            metadata_path = directory / "metadata.json"
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if _expired(metadata, current):
                for item in metadata.get("attachments", []):
                    _evict(Path(item["path"]))
                shutil.rmtree(directory, ignore_errors=True)
                removed += 1
    return removed


def touch_message(thread_id: str, now: float | None = None) -> None:
    thread_id = validate_thread_id(thread_id)
    with _LOCK:
        expire_thread(thread_id, now=now)
        metadata = _read_metadata(thread_id)
        if not metadata["attachments"]:
            return
        metadata["last_message_at"] = time.time() if now is None else now
        _write_metadata(thread_id, metadata)


def list_attachments(thread_id: str) -> list[dict]:
    thread_id = validate_thread_id(thread_id)
    with _LOCK:
        expire_thread(thread_id)
        return [_public(item) for item in _read_metadata(thread_id)["attachments"]]


def delete_attachment(thread_id: str, attachment_id: str) -> bool:
    thread_id = validate_thread_id(thread_id)
    with _LOCK:
        metadata = _read_metadata(thread_id)
        item = next(
            (entry for entry in metadata["attachments"] if entry["id"] == attachment_id),
            None,
        )
        if item is None:
            return False
        path = Path(item["path"])
        _evict(path)
        path.unlink(missing_ok=True)
        metadata["attachments"].remove(item)
        metadata["revision"] = int(metadata.get("revision", 0)) + 1
        if metadata["attachments"]:
            _write_metadata(thread_id, metadata)
        else:
            shutil.rmtree(_thread_dir(thread_id), ignore_errors=True)
        return True


def delete_all(thread_id: str) -> int:
    thread_id = validate_thread_id(thread_id)
    with _LOCK:
        metadata = _read_metadata(thread_id)
        for item in metadata["attachments"]:
            _evict(Path(item["path"]))
        count = len(metadata["attachments"])
        shutil.rmtree(_thread_dir(thread_id), ignore_errors=True)
        return count


@contextmanager
def conversation_scope(thread_id: str) -> Iterator[None]:
    token = _CURRENT_THREAD.set(validate_thread_id(thread_id))
    try:
        yield
    finally:
        _CURRENT_THREAD.reset(token)


def current_thread_id() -> str | None:
    return _CURRENT_THREAD.get()


def cache_scope() -> str:
    thread_id = current_thread_id()
    if thread_id is None:
        return "global"
    with _LOCK:
        metadata = _read_metadata(thread_id)
        revision = metadata.get("revision", 0)
        identities = ",".join(
            sorted(item["id"] for item in metadata.get("attachments", []))
        )
    return f"{thread_id}:{revision}:{identities}"


def list_visible_files(ext: str) -> list[str]:
    ext = ext.lower().lstrip(".")
    files: dict[str, str] = {}
    bundled = data_dir() / ext
    if bundled.is_dir():
        for path in bundled.glob(f"*.{ext}"):
            files[path.name.casefold()] = path.name

    thread_id = current_thread_id()
    if thread_id is not None:
        for item in list_attachments(thread_id):
            if item["ext"] == ext:
                filename = f"{item['nome']}.{ext}"
                files[filename.casefold()] = filename
    return sorted(files.values(), key=str.casefold)


def resolve_visible_path(name: str, ext: str) -> Path:
    ext = ext.lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Extensão não suportada")
    if not name or Path(name).name != name or name in (".", ".."):
        raise ValueError("Nome de arquivo inválido")

    thread_id = current_thread_id()
    if thread_id is not None:
        with _LOCK:
            expire_thread(thread_id)
            metadata = _read_metadata(thread_id)
            for item in metadata["attachments"]:
                if item["ext"] == ext and item["name"].casefold() == name.casefold():
                    path = Path(item["path"])
                    if path.is_file():
                        return path

    directory = (data_dir() / ext).resolve()
    path = (directory / f"{name}.{ext}").resolve()
    if path.parent != directory or not path.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    return path
