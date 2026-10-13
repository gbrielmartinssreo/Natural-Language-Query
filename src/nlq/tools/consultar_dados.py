"""Consultas estruturadas (Pandas) sobre CSV/XLSX.

A LLM não gera nem executa código: informa uma operação e parâmetros
validados contra as colunas reais da planilha. Nenhum ``eval``/``exec`` é
usado. O resultado é compacto e devolve apenas o necessário à resposta.

Integridade: ``n/a``, célula vazia, traço e vazio contam como ausência,
nunca como zero. Agregações numéricas reportam quantos valores foram
ignorados por não serem numéricos.

Filtros chegam como lista (nativa ou string JSON) validada, por exemplo::

    [{"coluna": "Problema", "operador": "contem", "valor": "racismo"}]

Referências de registros recuperados por busca semântica podem ser
informadas em ``refs`` (mesmo formato) para que a consulta estruturada
conte apenas esses registros, sem duplicação::

    [{"aba": "Eixo 3", "indice": 12}, {"aba": "Eixo 3", "indice": 7}]
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from time import perf_counter

import pandas as pd
from langchain_core.tools import tool

from nlq.data.loader import load_records
from nlq.paths import data_dir

__all__ = ["consultar_dados"]

OPERACOES = ("contar", "filtrar", "agregar", "agrupar", "ordenar", "metas", "distintos")

OPERADORES = (
    "igual",
    "diferente",
    "maior",
    "maior_igual",
    "menor",
    "menor_igual",
    "contem",
    "nao_contem",
    "vazio",
    "nao_vazio",
    "em",
)

AGREGACOES = ("contagem", "soma", "media", "minimo", "maximo")

# "valores" só existe em 'agrupar': reúne os valores distintos de uma
# coluna por grupo, preservando a transcrição original (consolidação).
AGREGACOES_AGRUPAR = (*AGREGACOES, "valores")

# Valores textuais que representam ausência explícita na planilha.
AUSENTES = {
    "n/a",
    "não se aplica",
    "nao se aplica",
    "-",
    "--",
}

LIMITE_PADRAO = 20
LIMITE_MAX = 100
LIMITE_CARACTERES = 300
# Consolidação: máximo de valores distintos por grupo e tamanho máximo de
# cada valor transcrito (preserva a transcrição exata dentro do teto).
LIMITE_VALORES = 50
LIMITE_VALOR = 2000
CACHE_MAX_ENTRIES = 8

# cache de DataFrames: caminho -> (fingerprint, {aba: DataFrame})
_DF_CACHE: dict[str, tuple[tuple[int, int], dict[str, pd.DataFrame]]] = {}


def _resolve_path(name: str, ext: str) -> Path:
    # Não permita subir diretórios, nem mesmo para outras pastas em sheets/.
    if not name or Path(name).name != name or name in (".", ".."):
        raise ValueError("Nome de arquivo inválido")

    pasta_formato = (data_dir() / ext).resolve()
    path = (pasta_formato / f"{name}.{ext}").resolve()
    if path.parent != pasta_formato:
        raise ValueError("Nome de arquivo inválido")

    if not path.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    return path


def _norm(value: object) -> str:
    return " ".join(str(value).strip().casefold().split())


PSEUDO_ABA = ("aba", "abas", "eixo", "eixos")


def _match_column(coluna: str, columns) -> str:
    """Resolve o nome de coluna ignorando caixa e espaços extras.

    "aba"/"eixo" (e plurais) resolvem para a coluna interna ``_aba``,
    coerente com ``agrupar_por`` e com a origem devolvida em ``_origem``.
    """
    alvo = _norm(coluna)

    for col in columns:
        if _norm(col) == alvo:
            return col

    if alvo in PSEUDO_ABA and "_aba" in columns:
        return "_aba"

    disponiveis = [str(c) for c in columns if not str(c).startswith("_")]
    raise ValueError(
        f"Coluna {coluna!r} não existe. Colunas disponíveis: "
        f"{', '.join(disponiveis)} (a aba de origem vem em _origem)"
    )


def _load_frames(path: Path) -> dict[str, pd.DataFrame]:
    """DataFrames por aba (CSV usa a chave ''), com cache por arquivo."""
    stat = path.stat()
    fingerprint = (stat.st_mtime_ns, stat.st_size)
    key = str(path)

    cached = _DF_CACHE.get(key)

    if cached is not None and cached[0] == fingerprint:
        return cached[1]

    records = load_records(path)

    if isinstance(records, dict):
        sheets = records
    else:
        sheets = {"": records}

    frames: dict[str, pd.DataFrame] = {}

    for aba, rows in sheets.items():
        frame = pd.DataFrame(rows)

        if frame.empty:
            frame = pd.DataFrame(columns=[])

        # _indice espelha build_documents(): posição 1-based na lista de
        # registros da aba, permitindo casar refs da busca semântica.
        frame.insert(0, "_indice", range(1, len(frame) + 1))
        frame["_aba"] = aba
        frames[aba] = frame

    # Entradas antigas do mesmo arquivo ficam obsoletas e o cache é
    # limitado (FIFO) para não crescer sem controle.
    for antigo in [k for k in _DF_CACHE if k == key]:
        del _DF_CACHE[antigo]

    while len(_DF_CACHE) >= CACHE_MAX_ENTRIES:
        _DF_CACHE.pop(next(iter(_DF_CACHE)))

    _DF_CACHE[key] = (fingerprint, frames)
    return frames


def _select_scope(frames: dict[str, pd.DataFrame], aba: str) -> pd.DataFrame:
    if aba and aba.strip():
        alvo = _norm(aba)

        for nome, frame in frames.items():
            if _norm(nome) == alvo:
                return frame

        parciais = [
            nome for nome in frames
            if nome and alvo in _norm(nome)
        ]

        if len(parciais) == 1:
            return frames[parciais[0]]

        disponiveis = ", ".join(repr(n) for n in frames)
        raise ValueError(
            f"Aba {aba!r} não encontrada. Abas disponíveis: {disponiveis}"
        )

    if not frames:
        raise ValueError("Arquivo sem abas ou registros consultáveis")
    return pd.concat(frames.values(), ignore_index=True)


def _as_number(value: object) -> float | None:
    """Lê números reais e decimais brasileiros sem transformar ausentes em zero.

    Exemplos: 12,5; 1.234,56; R$ 1.234,56. Percentuais e datas
    ficam fora das agregações genéricas para evitar confusão de unidade.
    """
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        try:
            return float(value) if pd.notna(value) else None
        except (ValueError, OverflowError):
            return None

    texto = str(value).strip().replace("\u00a0", " ")
    if not texto or texto.casefold() in AUSENTES or "%" in texto:
        return None

    texto = re.sub(r"^R\$\s*", "", texto, flags=re.IGNORECASE)
    texto = texto.replace(" ", "")

    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        numero = float(texto)
        return numero if pd.notna(numero) and abs(numero) != float("inf") else None
    except (TypeError, ValueError, OverflowError):
        return None


def _to_number(series: pd.Series) -> pd.Series:
    # Necessário para CSV, cujas células chegam como texto, e XLSX mistos.
    return pd.to_numeric(series.map(_as_number), errors="coerce")


def _is_blank(series: pd.Series) -> pd.Series:
    return series.isna() | series.astype("string").str.strip().eq("")


def _is_absent(series: pd.Series) -> pd.Series:
    texto = series.astype("string").str.strip().str.casefold()
    return _is_blank(series) | texto.isin(AUSENTES)


def _numeric_compare(series: pd.Series, operador: str, valor: float) -> pd.Series:
    numero = _to_number(series)

    if operador == "igual":
        return numero == valor
    if operador == "diferente":
        return numero.notna() & (numero != valor)
    if operador == "maior":
        return numero > valor
    if operador == "maior_igual":
        return numero >= valor
    if operador == "menor":
        return numero < valor
    if operador == "menor_igual":
        return numero <= valor

    raise ValueError(f"Operador inválido: {operador}")


def _string_compare(series: pd.Series, operador: str, valor: object) -> pd.Series:
    esquerda = series.astype("string").str.strip().str.casefold()
    direita = str(valor).strip().casefold()

    if operador == "igual":
        return esquerda.eq(direita)
    if operador == "diferente":
        return esquerda.ne(direita) & esquerda.notna()
    if operador == "maior":
        return esquerda.gt(direita) & esquerda.notna()
    if operador == "maior_igual":
        return esquerda.ge(direita) & esquerda.notna()
    if operador == "menor":
        return esquerda.lt(direita) & esquerda.notna()
    if operador == "menor_igual":
        return esquerda.le(direita) & esquerda.notna()

    raise ValueError(f"Operador inválido: {operador}")


def _condition(series: pd.Series, operador: str, valor: object) -> pd.Series:
    if operador == "vazio":
        # "Sem valor" inclui n/a, traço e não se aplica — a mesma
        # semântica de ausência usada pela operação 'metas'.
        return _is_absent(series)

    if operador == "nao_vazio":
        return ~_is_absent(series)

    if operador in ("contem", "nao_contem"):
        texto = series.astype("string").str.casefold()
        alvo = str(valor).casefold()
        contem = texto.str.contains(alvo, regex=False, na=False)
        return contem if operador == "contem" else ~contem

    if operador == "em":
        valores = valor if isinstance(valor, list) else [valor]
        numeros = [n for n in (_as_number(v) for v in valores) if n is not None]
        texto = series.astype("string").str.strip().str.casefold()
        alvos = {str(v).strip().casefold() for v in valores}
        match = texto.isin(alvos)

        if numeros:
            numero = _to_number(series)
            match = match | numero.isin(numeros)

        return match

    numero_valor = _as_number(valor)

    if numero_valor is not None:
        numero = _to_number(series)

        if numero.notna().any():
            return _numeric_compare(series, operador, numero_valor)

    return _string_compare(series, operador, valor)


def _como_lista(valor: list | str, campo: str) -> list:
    """Normaliza um parâmetro que pode vir como lista nativa ou JSON.

    O modelo pode enviar o argumento já estruturado (lista de objetos) ou
    como uma string JSON. Ambos são aceitos; a validação do conteúdo
    continua sendo feita por quem chama.
    """
    if valor is None:
        return []

    if isinstance(valor, str):
        if not valor.strip():
            return []

        try:
            valor = json.loads(valor)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{campo} deve ser um JSON válido (lista de objetos)"
            ) from exc

    if not isinstance(valor, list):
        raise ValueError(f"{campo} deve ser uma lista")

    return valor


def _parse_filters(filtros: list | str) -> list[dict]:
    dados = _como_lista(filtros, "filtros")

    validados = []

    for item in dados:
        if not isinstance(item, dict):
            raise ValueError("cada filtro deve ser um objeto com coluna/operador")

        coluna = item.get("coluna")
        operador = _norm(item.get("operador", ""))

        if not coluna:
            raise ValueError("cada filtro precisa de 'coluna'")

        if operador not in OPERADORES:
            raise ValueError(
                f"Operador {item.get('operador')!r} inválido. "
                f"Use: {', '.join(OPERADORES)}"
            )

        validados.append({
            "coluna": coluna,
            "operador": operador,
            "valor": item.get("valor"),
        })

    return validados


def _apply_filters(df: pd.DataFrame, filtros: list[dict]) -> pd.DataFrame:
    mascara = pd.Series(True, index=df.index)

    for filtro in filtros:
        coluna = _match_column(filtro["coluna"], df.columns)
        mascara &= _condition(df[coluna], filtro["operador"], filtro["valor"])

    return df[mascara]


def _parse_refs(
    refs: list | str,
    frames: dict[str, pd.DataFrame],
) -> list[tuple[str, int]]:
    """Converte refs da busca semântica em pares (aba, indice) únicos."""
    dados = _como_lista(refs, "refs")

    if not dados:
        return []

    abas_reais = [nome for nome in frames if nome]
    unica_aba = abas_reais[0] if len(abas_reais) == 1 else ""

    vistos: set[tuple[str, int]] = set()
    resultado: list[tuple[str, int]] = []

    for item in dados:
        aba = unica_aba
        indice = None

        if isinstance(item, dict):
            aba = item.get("aba") or item.get("sheet") or unica_aba
            indice = item.get("indice")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            aba, indice = item
        else:
            indice = item

        numero = _as_number(indice)

        if numero is None:
            raise ValueError(f"Referência inválida (indice): {item!r}")

        if not numero.is_integer() or numero < 1:
            raise ValueError(f"Referência inválida (indice não inteiro): {item!r}")

        chave = (str(aba), int(numero))

        if chave not in vistos:
            vistos.add(chave)
            resultado.append(chave)

    return resultado


def _apply_refs(
    df: pd.DataFrame,
    refs: list[tuple[str, int]],
) -> pd.DataFrame:
    if not refs:
        return df

    chaves = {
        (_norm(aba), indice)
        for aba, indice in refs
    }
    series = pd.Series(
        list(zip(df["_aba"].map(_norm), df["_indice"])),
        index=df.index,
    )
    return df[series.isin(chaves)]


def _cell(valor: object) -> object:
    if valor is None:
        return None

    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass

    texto = str(valor)

    if len(texto) > LIMITE_CARACTERES:
        return texto[:LIMITE_CARACTERES] + "…"

    return texto


def _num(valor: object) -> object:
    if valor is None:
        return None

    numero = float(valor)

    if numero.is_integer():
        return int(numero)

    return round(numero, 6)


def _aggregate(series: pd.Series, agregacao: str) -> dict:
    if agregacao == "contagem":
        return {"valor": int(len(series))}

    numero = _to_number(series)
    validos = int(numero.notna().sum())
    total = int(len(series))
    ausentes = total - validos

    resultado = {
        "valor": None,
        "valores_numericos": validos,
        "valores_ausentes_ou_nao_numericos": ausentes,
    }

    if validos == 0:
        resultado["aviso"] = (
            "Nenhum valor numérico disponível; n/a e vazios não são zero."
        )
        return resultado

    if agregacao == "soma":
        resultado["valor"] = _num(numero.sum())
    elif agregacao == "media":
        resultado["valor"] = _num(numero.mean())
    elif agregacao == "minimo":
        resultado["valor"] = _num(numero.min())
    elif agregacao == "maximo":
        resultado["valor"] = _num(numero.max())

    return resultado


def _ano_columns(columns) -> dict[str, int]:
    anos = {}

    for col in columns:
        if str(col).startswith("_"):
            continue

        achado = re.match(r"^ano\s*(\d+)", _norm(col))

        if achado:
            anos[col] = int(achado.group(1))

    return dict(sorted(anos.items(), key=lambda item: item[1]))


def _op_contar(df: pd.DataFrame, filtros: list[dict]) -> dict:
    total = int(len(df))
    correspondentes = int(len(_apply_filters(df, filtros)))
    percentual = round(correspondentes / total * 100, 2) if total else 0.0

    return {
        "operacao": "contar",
        "total_no_escopo": total,
        "correspondentes": correspondentes,
        "percentual": percentual,
    }


def _format_rows(df: pd.DataFrame, colunas: str, limite: int) -> tuple[list[dict], list[str]]:
    """Projeta registros preservando IDs da lista carregada pelo RAG."""
    if colunas and colunas.strip():
        nomes = [_match_column(c.strip(), df.columns) for c in colunas.split(",")]
    else:
        nomes = [c for c in df.columns if not str(c).startswith("_")]

    linhas = []
    for registro in df.head(limite).to_dict(orient="records"):
        linha = {nome: _cell(registro[nome]) for nome in nomes}
        linha["_origem"] = {
            "aba": registro["_aba"] or None,
            "indice": int(registro["_indice"]),
        }
        linhas.append(linha)

    return linhas, nomes


def _op_filtrar(
    df: pd.DataFrame,
    filtros: list[dict],
    colunas: str,
    limite: int,
) -> dict:
    correspondentes = _apply_filters(df, filtros)
    total = int(len(correspondentes))
    linhas, nomes = _format_rows(correspondentes, colunas, limite)

    return {
        "operacao": "filtrar",
        "total_correspondentes": total,
        "retornadas": len(linhas),
        "truncado": total > limite,
        "colunas": nomes,
        "linhas": linhas,
    }


def _op_ordenar(
    df: pd.DataFrame,
    filtros: list[dict],
    ordenar_por: str,
    ordem: str,
    colunas: str,
    limite: int,
) -> dict:
    if not ordenar_por:
        raise ValueError("A operação 'ordenar' exige ordenar_por")
    chave = _match_column(ordenar_por, df.columns)
    sentido = _norm(ordem) or "desc"
    if sentido not in ("asc", "desc"):
        raise ValueError("ordem deve ser 'asc' ou 'desc'")

    filtrado = _apply_filters(df, filtros).copy()
    numeros = _to_number(filtrado[chave])
    # Só faça ordenação numérica quando os valores preenchidos forem
    # numéricos. Em colunas mistas, use texto e explicite o critério.
    preenchidos = ~_is_absent(filtrado[chave])
    numerico = bool(preenchidos.any() and numeros[preenchidos].notna().all())
    if numerico:
        filtrado["__nlq_sort"] = numeros
        criterio = "numerico"
    else:
        filtrado["__nlq_sort"] = filtrado[chave].astype("string").str.casefold()
        criterio = "texto"

    ordenado = filtrado.sort_values(
        "__nlq_sort", ascending=(sentido == "asc"),
        na_position="last", kind="mergesort",
    )
    total = len(ordenado)
    linhas, nomes = _format_rows(ordenado, colunas, limite)
    return {
        "operacao": "ordenar", "por": chave, "ordem": sentido,
        "criterio": criterio, "total_correspondentes": total,
        "retornadas": len(linhas), "truncado": total > limite,
        "colunas": nomes, "linhas": linhas,
    }


def _op_agregar(
    df: pd.DataFrame,
    filtros: list[dict],
    coluna: str,
    agregacao: str,
) -> dict:
    if not coluna:
        raise ValueError("A operação 'agregar' exige o parâmetro coluna")

    if not agregacao or _norm(agregacao) not in AGREGACOES:
        raise ValueError(
            f"Agregação inválida. Use: {', '.join(AGREGACOES)}"
        )

    nome_coluna = _match_column(coluna, df.columns)
    filtrado = _apply_filters(df, filtros)
    resultado = _aggregate(filtrado[nome_coluna], _norm(agregacao))

    return {
        "operacao": "agregar",
        "coluna": nome_coluna,
        "agregacao": _norm(agregacao),
        "registros_no_escopo": int(len(filtrado)),
        **resultado,
    }


def _parse_group_keys(agrupar_por: str, columns) -> tuple[list[str], list[str]]:
    """Converte 'aba, Medida' em colunas internas e rótulos legíveis.

    "aba"/"eixo" (e plurais) resolvem para ``_aba``. Colunas repetidas são
    ignoradas preservando a ordem de aparição.
    """
    partes = [p.strip() for p in str(agrupar_por).split(",") if p.strip()]

    if not partes:
        raise ValueError("A operação 'agrupar' exige o parâmetro agrupar_por")

    chaves: list[str] = []
    rotulos: list[str] = []

    for parte in partes:
        if _norm(parte) in PSEUDO_ABA:
            chave, rotulo = "_aba", "aba"
        else:
            chave = _match_column(parte, columns)
            rotulo = chave

        if chave not in chaves:
            chaves.append(chave)
            rotulos.append(rotulo)

    return chaves, rotulos


def _valores_distintos(series: pd.Series) -> list[str]:
    """Valores únicos na ordem original, preservando a transcrição exata.

    Ausentes (vazio, n/a, traço) não entram na lista; eles continuam
    contabilizados por ``total_registros``.
    """
    ausentes = _is_absent(series)
    valores: list[str] = []

    for presente, valor in zip(~ausentes, series):
        if not presente:
            continue

        texto = str(valor)

        if len(texto) > LIMITE_VALOR:
            texto = texto[:LIMITE_VALOR] + "…"

        if texto not in valores:
            valores.append(texto)

    return valores


def _refs_por_aba(grupo: pd.DataFrame) -> dict[str, list[int]]:
    """Índices de origem do grupo, agrupados por aba (compacto)."""
    refs: dict[str, list[int]] = {}

    for aba, indice in zip(grupo["_aba"], grupo["_indice"]):
        chave = "" if pd.isna(aba) else str(aba)
        refs.setdefault(chave, []).append(int(indice))

    for indices in refs.values():
        indices.sort()

    return refs


def _op_agrupar(
    df: pd.DataFrame,
    filtros: list[dict],
    agrupar_por: str,
    coluna: str,
    agregacao: str,
    limite: int,
) -> dict:
    chaves, rotulos = _parse_group_keys(agrupar_por, df.columns)
    filtrado = _apply_filters(df, filtros)
    agregacao = _norm(agregacao) or "contagem"

    if agregacao not in AGREGACOES_AGRUPAR:
        raise ValueError(
            f"Agregação inválida. Use: {', '.join(AGREGACOES_AGRUPAR)}"
        )

    nome_valor = None

    if agregacao != "contagem":
        if not coluna:
            raise ValueError(
                "Agregações e 'valores' em 'agrupar' exigem o parâmetro coluna"
            )
        nome_valor = _match_column(coluna, df.columns)

    # Forma antiga (uma coluna, agregação clássica) é mantida por
    # compatibilidade; multi-coluna e 'valores' usam o campo "grupo".
    simples = len(rotulos) == 1 and agregacao != "valores"
    grupos = []

    for valor_grupo, grupo in filtrado.groupby(chaves, dropna=False, sort=False):
        if not isinstance(valor_grupo, tuple):
            valor_grupo = (valor_grupo,)

        etiquetas = {
            rotulo: ("" if pd.isna(val) else str(val))
            for rotulo, val in zip(rotulos, valor_grupo)
        }

        if agregacao == "valores":
            valores = _valores_distintos(grupo[nome_valor])
            total_valores = len(valores)
            item = {
                "grupo": etiquetas,
                "valores": valores[:LIMITE_VALORES],
                "total_valores": total_valores,
                "valores_truncados": total_valores > LIMITE_VALORES,
                "total_registros": int(len(grupo)),
                "_refs": _refs_por_aba(grupo),
            }
        else:
            info = (
                {"valor": int(len(grupo))}
                if agregacao == "contagem"
                else _aggregate(grupo[nome_valor], agregacao)
            )
            item = (
                {rotulos[0]: etiquetas[rotulos[0]], **info}
                if simples
                else {"grupo": etiquetas, **info}
            )

        grupos.append(item)

    if agregacao == "valores":
        grupos.sort(key=lambda item: item["total_registros"], reverse=True)
    else:
        grupos.sort(
            key=lambda item: (item["valor"] is not None, item["valor"] or 0),
            reverse=True,
        )

    saida = {
        "operacao": "agrupar",
        "por": rotulos[0] if simples else rotulos,
        "agregacao": agregacao,
        "total_registros": int(len(filtrado)),
        "total_grupos": len(grupos),
        "truncado": len(grupos) > limite,
        "grupos": grupos[:limite],
    }

    if agregacao == "valores":
        saida["coluna_valores"] = nome_valor

    return saida


def _op_metas(
    df: pd.DataFrame,
    filtros: list[dict],
    coluna: str,
) -> dict:
    filtrado = _apply_filters(df, filtros)
    anos = _ano_columns(df.columns)

    if coluna and coluna.strip():
        alvo = _match_column(coluna, df.columns)
        anos = {alvo: anos.get(alvo, 0)} if alvo in anos else {}

    if not anos:
        raise ValueError(
            "Nenhuma coluna de ano (ex.: 'Ano 1 - UF') encontrada para 'metas'"
        )

    serie = []

    for nome, numero in anos.items():
        valores = filtrado[nome]
        ausentes = int(_is_absent(valores).sum())
        total = int(len(valores))
        serie.append({
            "ano": numero,
            "coluna": nome,
            "definidas": total - ausentes,
            "ausentes": ausentes,
        })

    return {
        "operacao": "metas",
        "registros_no_escopo": int(len(filtrado)),
        "serie": serie,
        "nota": "n/a e vazios contam como ausentes, nunca como zero.",
    }


def _op_distintos(
    df: pd.DataFrame,
    filtros: list[dict],
    coluna: str,
    limite: int,
) -> dict:
    if not coluna:
        raise ValueError("A operação 'distintos' exige o parâmetro coluna")

    nome_coluna = _match_column(coluna, df.columns)
    filtrado = _apply_filters(df, filtros)
    valores = filtrado[nome_coluna][~_is_absent(filtrado[nome_coluna])]

    unicos = list(dict.fromkeys(valores.astype(str).str.strip()))
    unicos.sort()

    return {
        "operacao": "distintos",
        "coluna": nome_coluna,
        "total_distintos": len(unicos),
        "truncado": len(unicos) > limite,
        "valores": unicos[:limite],
    }


def _executar(
    df: pd.DataFrame,
    operacao: str,
    filtros: list[dict],
    coluna: str,
    agregacao: str,
    agrupar_por: str,
    colunas: str,
    limite: int,
    ordenar_por: str,
    ordem: str,
) -> dict:
    if operacao == "contar":
        return _op_contar(df, filtros)
    if operacao == "filtrar":
        return _op_filtrar(df, filtros, colunas, limite)
    if operacao == "agregar":
        return _op_agregar(df, filtros, coluna, agregacao)
    if operacao == "agrupar":
        return _op_agrupar(
            df, filtros, agrupar_por, coluna, agregacao, limite
        )
    if operacao == "ordenar":
        return _op_ordenar(df, filtros, ordenar_por, ordem, colunas, limite)
    if operacao == "metas":
        return _op_metas(df, filtros, coluna)
    if operacao == "distintos":
        return _op_distintos(df, filtros, coluna, limite)

    raise ValueError(
        f"Operação {operacao!r} inválida. Use: {', '.join(OPERACOES)}"
    )


@tool
def consultar_dados(
    name: str,
    ext: str,
    operacao: str,
    aba: str = "",
    coluna: str = "",
    agregacao: str = "",
    agrupar_por: str = "",
    filtros: list[dict] | str = "",
    colunas: str = "",
    refs: list[dict] | str = "",
    limite: int = LIMITE_PADRAO,
    ordenar_por: str = "",
    ordem: str = "desc",
) -> str:
    """
    Consulta planilhas CSV/XLSX com Pandas, usando operações tabulares
    exatas sobre colunas identificadas no arquivo. Não exige cálculos:
    também localiza registros por condições textuais.

    ESCOLHA DA OPERAÇÃO PELO FORMATO DA RESPOSTA:
    - filtrar: quando o usuário precisa de linhas individuais, com suas
      colunas e referências, inclusive se várias linhas forem parecidas.
    - agrupar com agregacao="valores": quando a resposta pede entidades
      ou combinações distintas, reunindo os diferentes valores associados
      a cada grupo, SEM repetir linhas equivalentes na resposta da LLM.
      Escolha agrupar_por com uma ou mais colunas reais da planilha;
      coluna indica o campo cujos valores distintos serão reunidos.
      Não invente colunas nem pressuponha nomes ou domínios específicos.
    - agrupar com agregacao="contagem", "soma", "media", "minimo" ou
      "maximo": quando o usuário precisa de totais por grupo.
    - contar, agregar, ordenar, metas e distintos: use conforme a
      necessidade de contagem, cálculo, ranking, metas ou valores únicos.

    IMPORTANTE SOBRE CONSOLIDAÇÃO:
    - Quando o mesmo item aparece em várias linhas e a pergunta pede
      itens distintos mais valores associados, prefira 'agrupar' em vez
      de enviar todas as linhas com 'filtrar' para a LLM consolidar.
    - Se a pergunta exige cada ocorrência, use 'filtrar'. Não aplique
      deduplicação automaticamente: linhas repetidas podem ser legítimas.
    - A operação 'agrupar' com 'valores' informa total_registros,
      total_valores e referências (_refs) agrupadas por aba.
    - 'valores' preserva os textos originais dos valores retornados,
      mas há limites: até 50 valores por grupo, e até 2000 caracteres
      por valor. Observe valores_truncados e qualquer reticência.
      Não afirme transcrição integral se algum texto estiver cortado.
    - O limite de até 100 grupos/linhas é indicado por 'truncado'.
      Nunca apresente resultados parciais como exaustivos.

    FILTROS E ESCOPO:
    - filtros é uma lista de {coluna, operador, valor}; múltiplos filtros
      são combinados por AND, tanto em 'filtrar' quanto em 'agrupar'.
    - 'contem' faz correspondência textual parcial, sem exigir semântica.
    - Operadores: igual, diferente, maior, maior_igual, menor,
      menor_igual, contem, nao_contem, vazio, nao_vazio, em.
    - aba="" consulta todas as abas; em agrupamentos, o alias 'aba'
      em agrupar_por permite separar resultados por origem.
    - Use buscar_semantico apenas se os critérios dependerem de
      significado, sinônimos ou interpretação conceitual; refs limita
      o Pandas somente aos candidatos recuperados, sem garantir
      cobertura semântica completa.
    - Não use create_json para cálculos resolvidos por esta ferramenta.

    EXEMPLOS GENÉRICOS:
    - Pedidos de cada linha correspondente: operacao="filtrar",
      filtros=[{"coluna":"Status","operador":"igual","valor":"Ativo"}].
    - Pedidos de itens únicos com valores associados:
      operacao="agrupar", agrupar_por="aba, Categoria",
      coluna="Fornecedor", agregacao="valores", com filtros opcionais.
      Os nomes das colunas são ilustrativos; consulte o esquema real.

    Args:
        name: Nome do arquivo sem extensão.
        ext: Extensão: csv ou xlsx.
        operacao: contar, filtrar, agregar, agrupar, ordenar, metas,
            distintos.
        aba: Aba específica. Vazio consulta todas as abas.
        coluna: Coluna-alvo de agregação ou valores reunidos por grupo.
        agregacao: contagem, soma, media, minimo, maximo; no agrupar,
            também 'valores' para consolidação sem cálculo numérico.
        agrupar_por: Uma ou mais colunas separadas por vírgula;
            'aba'/'eixo' representa a aba de origem.
        filtros: Lista de {coluna, operador, valor} ou string JSON.
        colunas: Campos projetados em filtrar/ordenar, separados por
            vírgula; 'aba' expõe a origem e _origem é sempre devolvido.
        refs: Lista de {aba, indice} recuperada pelo RAG, ou JSON.
        limite: Até 100 linhas ou grupos retornados (padrão 20).
        ordenar_por: Coluna usada na operação ordenar.
        ordem: 'asc' ou 'desc' para ordenar.
    """

    inicio = perf_counter()
    resultado = None
    status = "erro"
    print("[TOOL] consultar_dados inicio", flush=True)
    try:
        ext = ext.lower().lstrip(".")

        if ext not in ("csv", "xlsx"):
            raise ValueError("Extensão não suportada")

        operacao = _norm(operacao)

        if operacao not in OPERACOES:
            raise ValueError(
                f"Operação {operacao!r} inválida. Use: {', '.join(OPERACOES)}"
            )

        try:
            limite = int(limite)
        except (TypeError, ValueError) as exc:
            raise ValueError("limite deve ser um número inteiro") from exc

        limite = max(1, min(LIMITE_MAX, limite))

        path = _resolve_path(name, ext)
        frames = _load_frames(path)
        escopo = _select_scope(frames, aba)

        filtros_validados = _parse_filters(filtros)
        refs_informadas = refs is not None and refs != ""
        refs_validadas = _parse_refs(refs, frames)

        # Uma lista vazia de candidatos semânticos não é sinônimo de "tudo".
        if refs_informadas and not refs_validadas:
            resultado = json.dumps({
                "operacao": operacao, "arquivo": f"{name}.{ext}",
                "registros_no_escopo": 0,
                "aviso": "Lista explícita de referências vazia; nenhuma consulta aplicada.",
            }, ensure_ascii=False, separators=(",", ":"))
            status = "ok"
            return resultado

        total_antes = int(len(escopo))
        escopo = _apply_refs(escopo, refs_validadas)

        if refs_validadas and escopo.empty:
            resultado = json.dumps({
                "operacao": operacao,
                "aviso": (
                    "Nenhuma referência corresponde a registros existentes; "
                    "verifique aba e indice."
                ),
                "refs_recebidas": len(refs_validadas),
            }, ensure_ascii=False, separators=(",", ":"))
            status = "ok"
            return resultado

        resultado = _executar(
            escopo,
            operacao,
            filtros_validados,
            coluna,
            agregacao,
            agrupar_por,
            colunas,
            limite,
            ordenar_por,
            ordem,
        )

        resultado["arquivo"] = f"{name}.{ext}"

        if aba and aba.strip():
            resultado["aba"] = aba

        if refs_validadas:
            resultado["refs"] = {
                "recebidas": len(refs_validadas),
                "unicas": len(refs_validadas),
                "registros_no_escopo": total_antes,
                "registros_encontrados": len(escopo),
            }

        resultado = json.dumps(resultado, ensure_ascii=False, separators=(",", ":"))
        status = "ok"
        return resultado
    finally:
        duracao = perf_counter() - inicio
        caracteres = len(resultado) if isinstance(resultado, str) else 0
        print(
            f"[PERF] tool=consultar_dados status={status} "
            f"tempo={duracao:.4f}s caracteres={caracteres}",
            flush=True,
        )
