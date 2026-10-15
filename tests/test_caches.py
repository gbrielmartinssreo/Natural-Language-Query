"""Limpeza dos caches em RAM e em disco (endpoint /api/limpar-cache)."""

import os
import tempfile
import unittest
from pathlib import Path

import nlq.api as api
from nlq.data.semantic_search import (
    SemanticIndex,
    _INDEX_CACHE,
    _QUERY_CACHE,
    limpar_indices,
)
from nlq.tools.consultar_dados import _DF_CACHE, limpar_cache_dataframes


class TestLimparDataFrames(unittest.TestCase):
    def test_zera_e_devolve_quantidade(self):
        _DF_CACHE["/tmp/a.xlsx"] = ((0, 0), {"": []})
        _DF_CACHE["/tmp/b.xlsx"] = ((0, 0), {"": []})

        removidos = limpar_cache_dataframes()

        self.assertEqual(removidos, 2)
        self.assertEqual(_DF_CACHE, {})


class TestLimparIndices(unittest.TestCase):
    def setUp(self):
        _INDEX_CACHE.clear()
        _QUERY_CACHE.clear()

    def tearDown(self):
        _INDEX_CACHE.clear()
        _QUERY_CACHE.clear()

    def test_zera_caches_de_ram(self):
        _INDEX_CACHE[Path("/tmp/a.xlsx")] = SemanticIndex(
            fingerprint=(0, 0), documents=[], vectors=[]
        )
        _QUERY_CACHE["consulta"] = [0.0]

        liberado = limpar_indices(disco=False)

        self.assertEqual(liberado["indice_ram"], 1)
        self.assertEqual(liberado["consulta_ram"], 1)
        self.assertEqual(liberado["arquivos_disco"], 0)
        self.assertEqual(_INDEX_CACHE, {})
        self.assertEqual(_QUERY_CACHE, {})

    def test_remove_pickles_do_disco(self):
        with tempfile.TemporaryDirectory() as tmp:
            anterior = os.environ.get("XDG_CACHE_HOME")
            os.environ["XDG_CACHE_HOME"] = tmp

            try:
                pasta = Path(tmp) / "nlq-cache"
                pasta.mkdir(parents=True, exist_ok=True)

                arquivo = pasta / "index-fake.pkl"
                arquivo.write_bytes(b"0123456789")

                liberado = limpar_indices(disco=True)

                self.assertEqual(liberado["arquivos_disco"], 1)
                self.assertEqual(liberado["bytes_disco"], 10)
                self.assertFalse(arquivo.exists())

            finally:
                if anterior is None:
                    os.environ.pop("XDG_CACHE_HOME", None)
                else:
                    os.environ["XDG_CACHE_HOME"] = anterior


class TestLimparCacheEndpoint(unittest.TestCase):
    def test_consulta_ativa_retorna_409(self):
        with api._consultas_lock:
            api._consultas_ativas.add("thread-x")

        try:
            resposta = api.clear_cache()
            self.assertEqual(resposta.status_code, 409)
        finally:
            with api._consultas_lock:
                api._consultas_ativas.discard("thread-x")

    def test_limpa_e_devolve_totais(self):
        original_df = api.limpar_cache_dataframes
        original_sem = api.limpar_indices

        api.limpar_cache_dataframes = lambda: 3
        api.limpar_indices = lambda disco=True: {
            "indice_ram": 1,
            "consulta_ram": 2,
            "arquivos_disco": 4,
            "bytes_disco": 40,
        }

        try:
            resposta = api.clear_cache()
        finally:
            api.limpar_cache_dataframes = original_df
            api.limpar_indices = original_sem

        self.assertEqual(resposta["status"], "ok")
        self.assertEqual(resposta["dataframes_ram"], 3)
        self.assertEqual(resposta["indice_ram"], 1)
        self.assertEqual(resposta["consulta_ram"], 2)
        self.assertEqual(resposta["arquivos_disco"], 4)
        self.assertEqual(resposta["bytes_disco"], 40)


if __name__ == "__main__":
    unittest.main()
