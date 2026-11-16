"""Configurações JSON de gráficos: sem executar código produzido pelo modelo."""

import json
import math
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, model_validator


class SerieGrafico(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str = Field(min_length=1, max_length=120)
    valores: list[StrictInt | StrictFloat | None] = Field(min_length=1, max_length=200)


class EntradaGrafico(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: Literal["bar", "line", "pie", "doughnut"]
    titulo: str = Field(min_length=1, max_length=200)
    rotulos: list[str] = Field(min_length=1, max_length=200)
    series: list[SerieGrafico] = Field(min_length=1, max_length=8)
    fonte: str = Field(min_length=1, max_length=400)
    eixo_x: str = Field(default="", max_length=120)
    eixo_y: str = Field(default="", max_length=120)
    horizontal: bool = False
    contagem: bool = False

    @model_validator(mode="after")
    def validar_dados(self):
        circular = self.tipo in ("pie", "doughnut")
        if any(not r.strip() or len(r) > 200 for r in self.rotulos):
            raise ValueError("Rótulos devem ter de 1 a 200 caracteres.")
        if circular and len(self.series) != 1:
            raise ValueError("Pizza e rosca aceitam uma única série.")
        for serie in self.series:
            if len(serie.valores) != len(self.rotulos):
                raise ValueError("Cada série precisa de um valor por rótulo.")
            numeros = [v for v in serie.valores if v is not None]
            if not numeros or any(not math.isfinite(v) for v in numeros):
                raise ValueError("Use números finitos; não gere gráficos sem dados.")
            if circular and (len(numeros) != len(serie.valores)
                             or any(v < 0 for v in numeros) or not any(numeros)):
                raise ValueError("Pizza e rosca exigem valores não negativos e total positivo.")
        return self


CORES = ["#3b82f6", "#f59e0b", "#10b981", "#ef4444",
         "#8b5cf6", "#06b6d4", "#ec4899", "#64748b"]


def montar_grafico(entrada: EntradaGrafico) -> dict:
    circular = entrada.tipo in ("pie", "doughnut")
    datasets = []
    for i, serie in enumerate(entrada.series):
        cor = CORES[i % len(CORES)]
        datasets.append({
            "label": serie.nome,
            "data": serie.valores,
            "backgroundColor": [CORES[j % len(CORES)] for j in range(len(entrada.rotulos))]
                if circular else cor,
            "borderColor": "#ffffff" if circular else cor,
            "borderWidth": 2,
        })
    options = {
        "responsive": True,
        "maintainAspectRatio": False,
        "locale": "pt-BR",
        "plugins": {
            "title": {
                "display": True,
                "text": entrada.titulo,
                "font": {"size": 18},
                "padding": {"bottom": 20},
            },
            "legend": {
                "display": circular or len(entrada.series) > 1,
                "position": "bottom",
            },
            "tooltip": {
                "enabled": True,
            },
        },
        "layout": {"padding": 12},
    }

    if not circular:
        horizontal = entrada.horizontal and entrada.tipo == "bar"
        eixo_valor = "x" if horizontal else "y"
        eixo_categoria = "y" if horizontal else "x"

        options["indexAxis"] = "y" if horizontal else "x"
        options["scales"] = {
            eixo_categoria: {
                "title": {
                    "display": bool(entrada.eixo_x),
                    "text": entrada.eixo_x,
                },
                "grid": {"display": False},
                "ticks": {"autoSkip": True, "maxRotation": 45},
            },
            eixo_valor: {
                "beginAtZero": True,
                "title": {
                    "display": bool(entrada.eixo_y),
                    "text": entrada.eixo_y,
                },
                "ticks": {"precision": 0} if entrada.contagem else {},
            },
        }

    return {"tipo": "grafico", "titulo": entrada.titulo, "fonte": entrada.fonte,
            "entrada": entrada.model_dump(),
            "config": {"type": entrada.tipo,
                       "data": {"labels": entrada.rotulos, "datasets": datasets},
                       "options": options}}


@tool(args_schema=EntradaGrafico)
def gerar_grafico(tipo: str, titulo: str, rotulos: list[str],
                  series: list[SerieGrafico], fonte: str,
                  eixo_x: str = "", eixo_y: str = "",
                  horizontal: bool = False, contagem: bool = False) -> str:
    """Cria um gráfico no chat usando dados já obtidos pelas ferramentas de consulta.

    Consulte e agregue os dados com consultar_dados antes desta chamada. Não
    invente números nem trate trechos retornados pelo RAG como totais completos.
    Use bar para comparar categorias, line para evolução temporal e pie ou
    doughnut para partes de um total. Cada série contém nome e valores na
    mesma ordem dos rotulos. Informe em fonte o arquivo, aba e agregação usados.
    Valores ausentes podem ser null em barras e linhas. Limite: 200 rótulos,
    8 séries; faça agregação antes se necessário. A interface exibe o gráfico
    automaticamente: não copie este JSON na resposta textual.
    """
    entrada = EntradaGrafico(tipo=tipo, titulo=titulo, rotulos=rotulos,
                             series=series, fonte=fonte,
                             eixo_x=eixo_x, eixo_y=eixo_y,
                             horizontal=horizontal, contagem=contagem)
    return json.dumps(montar_grafico(entrada), ensure_ascii=False, allow_nan=False)


def graficos_do_turno(messages) -> list[dict]:
    """Extrai só resultados de tools bem-sucedidas após a última mensagem humana."""
    inicio = 0
    for i, msg in enumerate(messages):
        if getattr(msg, "type", None) == "human":
            inicio = i + 1
    graficos = []
    vistos = set()
    for msg in messages[inicio:]:
        if (getattr(msg, "type", None) != "tool"
                or getattr(msg, "name", None) != "gerar_grafico"
                or getattr(msg, "status", "success") != "success"):
            continue
        try:
            grafico = json.loads(msg.content)
            # Reconstrói a configuração apenas com campos permitidos.
            config = grafico["config"]
            entrada = EntradaGrafico(
                tipo=config["type"], titulo=grafico["titulo"],
                fonte=grafico["fonte"], rotulos=config["data"]["labels"],
                series=[{"nome": s["label"], "valores": s["data"]}
                        for s in config["data"]["datasets"]],
            )
            # Novos resultados preservam todos os parâmetros validados.
            # Resultados antigos continuam usando a reconstrução acima.
            if "entrada" in grafico:
                entrada = EntradaGrafico.model_validate(grafico["entrada"])
            seguro = montar_grafico(entrada)
            chave = json.dumps(seguro, sort_keys=True, ensure_ascii=False)
            if chave not in vistos:
                vistos.add(chave)
                graficos.append(seguro)
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
    return graficos
