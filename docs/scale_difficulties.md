# Escala de Dificuldade das Planilhas

Referência para dimensionar o **parser** (camada de dados). Não descreve o
fluxo do agente — ver [`architecture.md`](architecture.md).

| Nível | Tipo                        | Alvo            |
|-------|-----------------------------|-----------------|
| 1     | CSV limpo                   | **Alcançável hoje** |
| 2     | XLSX simples                | **Alcançável hoje** |
| 3     | XLSX semi-estruturado       | Parcial — regiões e mesclas verticais tratadas |
| 4     | Planilha corporativa infernal | Acessível, não confiável |

## Teto atual

O carregamento vive em `src/nlq/data/loader.py` (CSV e XLSX) e a descoberta de
estrutura em `src/nlq/data/schema.py` (via `xldetect`):

- **CSV** — `csv.DictReader` com fallback de codificação
  (`utf-8-sig` → `utf-8` → `cp1252` → `latin-1`).
- **XLSX** — `xldetect` detecta as **regiões tabulares** de cada aba (limites,
  linha de cabeçalho, largura); o loader lê apenas essas regiões com
  `openpyxl` (`data_only=True`), reconstrói **mesclagens verticais** e descarta
  linhas totalmente vazias.

O nível alcançável hoje é o **2** com folga: XLSX com várias abas e uma ou mais
tabelas por aba, com cabeçalho detectado.

O nível 3 é **parcialmente tratado**:

| Feature do nível 3/4 | O que o parser entrega |
|-----------------------|-------------------------|
| título/linhas antes do cabeçalho | a região começa no cabeçalho detectado |
| múltiplos blocos na mesma aba | uma região por bloco (o schema lista as regiões) |
| células mescladas **verticais** | valor repetido nas linhas da mescla |
| células mescladas horizontais | `None` (não reconstruídas) |
| cabeçalho multinível | coluna nomeada pelo 1º nível |
| fórmula sem cache | `None` (por `data_only=True`) |
| abas ocultas | também são lidas |

Cabeçalhos ausentes, vazios ou duplicados recebem nomes gerados (`coluna_N`,
sufixo `_2`) por `make_headers`. Quando o `xldetect` não encontra nenhuma região
em uma aba, o loader preserva as células não vazias com nomes genéricos e emite
um aviso.

O nível 4 continua **acessível mas não confiável**: mesclas horizontais,
cabeçalhos multinível e significado por cor não são interpretados. O exemplo
concreto, `sheets/xlsx/MATRIZ ENCAMINHADA - FINAL.xlsx`, retorna dados, mas
interpretá-los exige que o LLM deduza a estrutura — o que contraria o princípio
de fidelidade.

## Contenção de payload

`create_json` bloqueia extração acima de **20.000 caracteres**
(`EXTRACAO_BLOQUEADA_POR_TAMANHO`) e orienta usar `buscar_semantico` (assunto)
ou `consultar_dados` (cálculo exato). O teto de geração do modelo é
`NLQ_MAX_TOKENS` (padrão **5000**). Para perguntas de conteúdo/agregação, o
caminho preferido é `consultar_dados`, que devolve só o necessário.

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

Fechar os níveis 3 e 4 exige tratar mesclagens horizontais e cabeçalho
multinível no parser. A evolução planejada não depende só de cache: o objetivo é
manter os dados localmente e enviar ao LLM somente o resultado relevante, usando
execução tabular (`consultar_dados`) para consultas exatas e busca semântica
(`buscar_semantico`) para conteúdo textual. Ver
[`possible_implements.md`](possible_implements.md) §§1–2.
