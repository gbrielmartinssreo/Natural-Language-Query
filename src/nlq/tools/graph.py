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
        "plugins": {"title": {"display": True, "text": entrada.titulo}},
    }
    if not circular:
        options["scales"] = {"y": {"beginAtZero": True}}
    return {"tipo": "grafico", "titulo": entrada.titulo, "fonte": entrada.fonte,
            "config": {"type": entrada.tipo,
                       "data": {"labels": entrada.rotulos, "datasets": datasets},
                       "options": options}}


@tool(args_schema=EntradaGrafico)
def gerar_grafico(tipo: str, titulo: str, rotulos: list[str],
                  series: list[SerieGrafico], fonte: str) -> str:
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
                             series=series, fonte=fonte)
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
            seguro = montar_grafico(entrada)
            chave = json.dumps(seguro, sort_keys=True, ensure_ascii=False)
            if chave not in vistos:
                vistos.add(chave)
                graficos.append(seguro)
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
    return graficos
