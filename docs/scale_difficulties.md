# Escala de Dificuldade das Planilhas

Referência para dimensionar o **parser** (a tool de planilha). Não descreve o
fluxo do agente — ver [`architecture.md`](architecture.md).

| Nível | Tipo                        | Alvo            |
|-------|-----------------------------|-----------------|
| 1     | CSV limpo                   | **Alcançável hoje** |
| 2     | XLSX simples                | **Alcançável hoje** |
| 3     | XLSX semi-estruturado       | Parcial — lido cru |
| 4     | Planilha corporativa infernal | Acessível, não confiável |

## Teto atual

A tool `create_json` lê **CSV** (`csv.DictReader`, com fallback de codificação) e
**XLSX** (`openpyxl`, `read_only=True`, `data_only=True`), então o nível alcançável
hoje é o **2**: planilhas XLSX com várias abas, uma tabela por aba.

O nível 3 é **lido de forma bruta** — os dados chegam ao LLM, mas distorcidos.
`read_excel` faz `dict(zip(headers, row))` usando a primeira linha como cabeçalho,
o que implica:

| Feature do nível 3/4 | O que o parser entrega       |
|-----------------------|------------------------------|
| células mescladas     | `None` nas células fundidas  |
| cabeçalho multinível  | coluna nomeada pelo 1º nível |
| fórmula sem cache     | `None` (por `data_only=True`) |
| vários blocos na aba | uma tabela só                |
| abas ocultas          | também são lidas             |

O nível 4 está, portanto, **acessível mas não confiável**: o exemplo concreto,
`sheets/xlsx/MATRIZ ENCAMINHADA - FINAL.xlsx`, retorna JSON, mas interpretá-lo
exige que o LLM deduza a estrutura — o que contraria o princípio de fidelidade.
Fechar esse nível exige tratar mesclas e cabeçalho multinível no parser.

## Nível 1 — CSV limpo

- uma tabela
- cabeçalhos claros
- sem fórmulas
- tipos consistentes

## Nível 2 — XLSX simples

- uma ou mais abas
- tabelas relacionadas
- datas, moedas, percentuais
- algumas fórmulas

## Nível 3 — XLSX semi-estruturado

- título antes do cabeçalho
- linhas de totais
- células vazias
- subtabelas
- múltiplos blocos na mesma aba

## Nível 4 — Planilha corporativa infernal

- células mescladas
- cabeçalhos multinível
- cores com significado
- fórmulas
- abas auxiliares ocultas
- gráficos
- pivôs
- observações no meio da tabela

Além disso, todo o conteúdo volta no contexto do LLM a cada pergunta (o
`max_tokens` é 7000 no Groq e 10000 no OpenRouter). Para arquivos grandes, esse
payload tende a ser um gargalo maior que a própria leitura do XLSX.

A evolução planejada não depende apenas de cache: o objetivo é manter os dados
localmente e enviar ao LLM somente os registros relevantes, usando execução
tabular para consultas exatas e busca semântica para conteúdo textual. Ver
[`possible_implements.md`](possible_implements.md) §§1–2.
