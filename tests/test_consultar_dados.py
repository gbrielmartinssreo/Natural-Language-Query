"""Testes unitários da integração Pandas (executar com uv run pytest)."""

import importlib
import json

import pytest


@pytest.fixture()
def tool_module(monkeypatch, tmp_path):
    module = importlib.import_module("nlq.tools.consultar_dados")
    (tmp_path / "csv").mkdir()
    (tmp_path / "xlsx").mkdir()
    (tmp_path / "csv" / "teste.csv").write_text("fixture", encoding="utf-8")
    (tmp_path / "xlsx" / "teste.xlsx").write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(module, "data_dir", lambda: tmp_path)
    # M1 repete-se com atores diferentes (mesma medida, atores distintos).
    dados = {
        "Aba 1": [
            {"Medida": "M1", "Ator": "Ator A", "Grupo": "G1",
             "Status": "não", "Valor": "1,2", "Ano 1": "n/a"},
            {"Medida": "M1", "Ator": "Ator B", "Grupo": "G1",
             "Status": "sim", "Valor": "2,5", "Ano 1": "25%"},
        ],
        "Aba 2": [
            {"Medida": "M2", "Ator": "Ator A", "Grupo": "G2",
             "Status": "não", "Valor": "R$ 1.234,56", "Ano 1": None},
        ],
    }
    monkeypatch.setattr(
        module,
        "load_records",
        lambda path: dados if path.suffix == ".xlsx" else dados["Aba 1"],
    )
    module._DF_CACHE.clear()
    return module


def _run(module, ext="xlsx", **kwargs):
    args = {"name": "teste", "ext": ext, **kwargs}
    return json.loads(module.consultar_dados.invoke(args))


# --- compatibilidade com o comportamento existente --------------------

def test_soma_decimais_brasileiros(tool_module):
    result = _run(tool_module, operacao="agregar", coluna="Valor", agregacao="soma")
    assert result["valor"] == pytest.approx(1238.26)
    assert result["valores_numericos"] == 3


def test_nao_nao_e_ausente(tool_module):
    result = _run(tool_module, operacao="contar", filtros=[
        {"coluna": "Status", "operador": "nao_vazio"},
    ])
    assert result["correspondentes"] == 3


def test_refs_nao_duplica_e_preserva_origem(tool_module):
    refs = [{"aba": "Aba 1", "indice": 1}, {"aba": "Aba 1", "indice": 1}]
    result = _run(tool_module, operacao="filtrar", colunas="Status", refs=refs)
    assert result["total_correspondentes"] == 1
    assert result["linhas"][0]["_origem"] == {"aba": "Aba 1", "indice": 1}


def test_refs_explicitas_vazias_nao_consultam_arquivo_inteiro(tool_module):
    result = _run(tool_module, operacao="contar", refs=[])
    assert result["registros_no_escopo"] == 0


def test_ordenacao_numerica(tool_module):
    result = _run(tool_module, operacao="ordenar", ordenar_por="Valor", ordem="desc")
    assert result["linhas"][0]["_origem"] == {"aba": "Aba 2", "indice": 1}


def test_distintos_ignora_ausencias(tool_module):
    result = _run(tool_module, operacao="distintos", coluna="Ano 1")
    assert result["total_distintos"] == 1
    assert result["valores"] == ["25%"]


def test_nome_arquivo_nao_pode_subir_diretorio(tool_module):
    with pytest.raises(ValueError, match="Nome de arquivo inválido"):
        _run(tool_module, operacao="contar", name="../teste")


def test_agrupar_simples_mantem_forma_antiga(tool_module):
    result = _run(
        tool_module, operacao="agrupar",
        agrupar_por="Medida", agregacao="contagem",
    )
    assert result["por"] == "Medida"
    # Forma antiga: campos achatados (rótulo + valor).
    medidas = {g["Medida"]: g["valor"] for g in result["grupos"]}
    assert medidas == {"M1": 2, "M2": 1}


# --- filtros com múltiplas condições ----------------------------------

def test_filtros_multiplas_condicoes(tool_module):
    result = _run(tool_module, operacao="contar", filtros=[
        {"coluna": "Medida", "operador": "igual", "valor": "M1"},
        {"coluna": "Ator", "operador": "igual", "valor": "Ator B"},
    ])
    assert result["correspondentes"] == 1


# --- agrupamento por uma ou mais colunas ------------------------------

def test_agrupar_uma_coluna(tool_module):
    result = _run(
        tool_module, operacao="agrupar",
        agrupar_por="Ator", agregacao="contagem",
    )
    atores = {g["Ator"]: g["valor"] for g in result["grupos"]}
    assert atores == {"Ator A": 2, "Ator B": 1}


def test_agrupar_multiplas_colunas(tool_module):
    result = _run(
        tool_module, operacao="agrupar",
        agrupar_por="aba, Medida", agregacao="contagem",
    )
    assert result["por"] == ["aba", "Medida"]
    chaves = {
        (g["grupo"]["aba"], g["grupo"]["Medida"]): g["valor"]
        for g in result["grupos"]
    }
    assert chaves == {("Aba 1", "M1"): 2, ("Aba 2", "M2"): 1}


# --- consolidação de valores distintos --------------------------------

def test_consolidacao_reune_valores_distintos(tool_module):
    result = _run(
        tool_module, operacao="agrupar",
        agrupar_por="Grupo", coluna="Ator", agregacao="valores",
    )
    por_grupo = {g["grupo"]["Grupo"]: g for g in result["grupos"]}
    assert por_grupo["G1"]["valores"] == ["Ator A", "Ator B"]
    assert por_grupo["G1"]["total_valores"] == 2
    assert por_grupo["G1"]["total_registros"] == 2
    assert por_grupo["G2"]["valores"] == ["Ator A"]


def test_consolidacao_preserva_referencias_de_origem(tool_module):
    result = _run(
        tool_module, operacao="agrupar",
        agrupar_por="Grupo", coluna="Ator", agregacao="valores",
    )
    por_grupo = {g["grupo"]["Grupo"]: g for g in result["grupos"]}
    assert por_grupo["G1"]["_refs"] == {"Aba 1": [1, 2]}
    assert por_grupo["G2"]["_refs"] == {"Aba 2": [1]}


def test_consolidacao_nao_duplica_valores(tool_module):
    result = _run(
        tool_module, operacao="agrupar",
        agrupar_por="Medida", coluna="Medida", agregacao="valores",
    )
    # Cada medida aparece uma única vez dentro do próprio grupo.
    for grupo in result["grupos"]:
        assert len(grupo["valores"]) == len(set(grupo["valores"]))


def test_consolidacao_limite_de_valores(tool_module, monkeypatch):
    monkeypatch.setattr(tool_module, "LIMITE_VALORES", 1)
    result = _run(
        tool_module, operacao="agrupar",
        agrupar_por="Grupo", coluna="Ator", agregacao="valores",
    )
    g1 = next(g for g in result["grupos"] if g["grupo"]["Grupo"] == "G1")
    assert g1["total_valores"] == 2
    assert len(g1["valores"]) == 1
    assert g1["valores_truncados"] is True


# --- integridade de valores originais ---------------------------------

def test_preserva_valor_original(tool_module):
    result = _run(
        tool_module, operacao="filtrar", colunas="Valor",
        filtros=[{"coluna": "Valor", "operador": "igual", "valor": "R$ 1.234,56"}],
    )
    assert result["linhas"][0]["Valor"] == "R$ 1.234,56"


def test_consolidacao_preserva_valor_original(tool_module):
    result = _run(
        tool_module, operacao="agrupar",
        agrupar_por="Grupo", coluna="Valor", agregacao="valores",
    )
    g2 = next(g for g in result["grupos"] if g["grupo"]["Grupo"] == "G2")
    assert "R$ 1.234,56" in g2["valores"]


# --- abrangência, vazio e truncamento ---------------------------------

def test_consulta_todas_as_abas(tool_module):
    result = _run(tool_module, operacao="contar", aba="")
    assert result["total_no_escopo"] == 3


def test_resultado_vazio(tool_module):
    result = _run(tool_module, operacao="filtrar", colunas="Medida", filtros=[
        {"coluna": "Medida", "operador": "igual", "valor": "inexistente"},
    ])
    assert result["total_correspondentes"] == 0
    assert result["linhas"] == []


def test_truncamento_explicito(tool_module):
    result = _run(tool_module, operacao="filtrar", colunas="Medida", limite=1)
    assert result["retornadas"] == 1
    assert result["truncado"] is True


def test_agrupar_coluna_aba(tool_module):
    result = _run(
        tool_module, operacao="agrupar",
        agrupar_por="aba", agregacao="contagem",
    )
    abas = {g["aba"]: g["valor"] for g in result["grupos"]}
    assert abas == {"Aba 1": 2, "Aba 2": 1}
