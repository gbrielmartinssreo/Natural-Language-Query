"""Resolução de caminhos de recursos do NLQ.

Centraliza a diferença entre rodar em desenvolvimento (repositório) e
empacotado com PyInstaller (``sys.frozen``), para que prompts, skills,
frontend, planilhas e o arquivo ``.env`` sejam encontrados nos dois casos.

Regras:

- Recursos **internos** (frontend, prompts e skills) são distribuídos
  dentro do pacote: em desenvolvimento ficam no repositório; empacotados
  ficam em ``sys._MEIPASS``.
- Dados **do usuário** (``sheets/``) e credenciais (``.env``) ficam
  fora do pacote, ao lado do executável, para poderem ser editados sem
  reconstruir a aplicação.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ENV_VAR = ".env"


def is_frozen() -> bool:
    """True quando executando a partir de um binário do PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def _module_dir() -> Path:
    """Diretório do pacote ``nlq`` (``.../nlq``)."""
    return Path(__file__).resolve().parent


def _package_dir() -> Path:
    """Diretório do pacote ``nlq`` dentro do pacote distribuído."""
    if is_frozen():
        return Path(sys._MEIPASS) / "nlq"  # type: ignore[attr-defined]
    return _module_dir()


def _project_root() -> Path:
    """Raiz do repositório em desenvolvimento (``.../src/nlq`` -> ``...``)."""
    return _module_dir().parents[1]


def _executable_dir() -> Path:
    """Pasta que contém o executável empacotado."""
    return Path(sys.executable).resolve().parent


def frontend_dir() -> Path:
    """Pasta do frontend estático (``index.html``, ``style.css``, ``app.js``)."""
    if is_frozen():
        return Path(sys._MEIPASS) / "frontend"  # type: ignore[attr-defined]
    return _project_root() / "frontend"


def prompts_dir() -> Path:
    """Pasta dos prompts do agente."""
    return _package_dir() / "agent" / "prompts"


def skills_dir() -> Path:
    """Pasta das skills do agente."""
    return _package_dir() / "agent" / "skills"


def data_dir() -> Path:
    """Pasta externa com as planilhas do usuário (``sheets/``)."""
    if is_frozen():
        return _executable_dir() / "sheets"
    return _project_root() / "sheets"


def env_file() -> Path:
    """Arquivo ``.env`` com as credenciais e a seleção de provider."""
    if is_frozen():
        return _executable_dir() / _ENV_VAR
    return _project_root() / _ENV_VAR


def load_env() -> None:
    """Carrega o ``.env`` adequado sem sobrescrever variáveis já definidas."""
    from dotenv import load_dotenv

    load_dotenv(env_file(), override=False)
