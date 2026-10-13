"""Camada de dados: schema de planilhas e carregamento com cache."""

from .loader import clear_cache, get_schema, load_records
from .schema import build_schema

__all__ = ["build_schema", "clear_cache", "get_schema", "load_records"]
