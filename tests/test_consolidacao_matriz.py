"""Integridade e redução de volume da consolidação (planilha real).

Garante que a consolidação preserva todos os registros correspondentes
(mesma cobertura de origem) e reduz o volume enviado ao modelo. O teste
é ignorado quando a planilha de exemplo não está disponível.
"""

import json

import pytest

from nlq.paths import data_dir
from nlq.tools.consultar_dados import consultar_dados

MATRIZ = data_dir() / "xlsx" / "matriz.xlsx"

pytestmark = pytest.mark.skipif(
    not MATRIZ.is_file(), reason="matriz.xlsx indisponível"
)

FILTROS = [
    {"coluna": "Atores estratégicos - UF", "operador": "contem",
     "valor": "administração penitenciária"},
    {"coluna": "Atores estratégicos - UF", "operador": "contem",
     "valor": "Tribunal de Justiça"},
]
FILTROS_JSON = json.dumps(FILTROS, ensure_ascii=False)


def _run(**kw):
    return json.loads(
        consultar_dados.invoke({"name": "matriz", "ext": "xlsx", **kw})
    )


def test_consolidacao_reduz_volume_sem_perder_registros():
    bruto = _run(
        operacao="filtrar",
        colunas="Medida,Atores estratégicos - UF",
        filtros=FILTROS_JSON,
        limite=100,
    )
    consolidado = _run(
        operacao="agrupar",
        agrupar_por="aba, Medida",
        coluna="Atores estratégicos - UF",
        agregacao="valores",
        filtros=FILTROS_JSON,
        limite=100,
    )

    origens_bruto = {
        (linha["_origem"]["aba"], linha["_origem"]["indice"])
        for linha in bruto["linhas"]
    }
    origens_consolidado = set()
    for grupo in consolidado["grupos"]:
        for aba, indices in grupo["_refs"].items():
            origens_consolidado.update((aba, i) for i in indices)

    # Nenhuma correspondência válida é perdida nem inventada.
    assert origens_consolidado == origens_bruto
    assert consolidado["total_registros"] == bruto["total_correspondentes"]

    # As medidas distintas continuam todas representadas.
    medidas_bruto = {linha["Medida"] for linha in bruto["linhas"]}
    medidas_consolidado = {
        grupo["grupo"]["Medida"] for grupo in consolidado["grupos"]
    }
    assert medidas_consolidado == medidas_bruto

    # O volume consolidado é menor que o volume bruto.
    bruto_chars = len(json.dumps(bruto, ensure_ascii=False))
    consolidado_chars = len(json.dumps(consolidado, ensure_ascii=False))
    assert consolidado_chars < bruto_chars

    print(
        f"\n[CONSOLIDACAO] bruto={bruto_chars} chars -> "
        f"consolidado={consolidado_chars} chars "
        f"({(1 - consolidado_chars / bruto_chars) * 100:.1f}% menor)"
    )
