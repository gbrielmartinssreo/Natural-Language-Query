# Escala de Dificuldade das Planilhas

Referência para dimensionar o **parser** (a tool de planilha). Não descreve o
fluxo do agente — ver [`architecture.md`](architecture.md).

| Nível | Tipo                        | Alvo            |
|-------|-----------------------------|-----------------|
| 1     | CSV limpo                   | Escopo inicial   |
| 2     | XLSX simples                | —               |
| 3     | XLSX semi-estruturado       | —               |
| 4     | Planilha corporativa infernal | Desafio final |

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
