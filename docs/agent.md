# Agente

## 1. Papel

O agente é a camada de raciocínio e orquestração do NLQ. Ele recebe a pergunta em
linguagem natural, **consulta a planilha através de uma ferramenta** e devolve uma
resposta fiel e rastreável. Também **mantém o histórico da sessão** em memória,
de modo que um turno pode retomar o contexto do anterior.

O LLM é quem decide o que consultar, interpreta o JSON retornado e redige a
resposta — não há etapas rigidamente separadas no código.

## 2. Implementação atual

Definido em `create_nlq_agent()` — `src/nlq/agent/agent.py`. Há **dois modelos
candidatos**, e a escolha acontece em tempo de execução:

```python
checkpointer = InMemorySaver()

model1 = init_chat_model(
    "openai/gpt-oss-120b",
    model_provider="groq",
    temperature=0.1,
    timeout=60000,
    max_tokens=7000,
)


model2 = init_chat_model(
    "openrouter:qwen/qwen3-30b-a3b-instruct-2507",
    temperature=0.1,
    timeout=60000,
    max_tokens=10000,
)


if os.getenv("API_SELECT") == "groq" or not check_openrouter_key():
    model = model1
elif os.getenv("API_SELECT") == "openrouter" or check_openrouter_key():
    model = model2

tools = [create_json, lista_arquivos]

return create_agent(
    model=model,
    tools=tools,
    checkpointer=checkpointer,
    system_prompt=(
        load_prompt("prompts/system_base.md")
        + "\n\n"
        + load_prompt("prompts/specific_role.md")
    ),
)
```

> **Atenção** — os dois modelos são construídos incondicionalmente, antes da
> escolha. Sem `GROQ_API_KEY`, a construção do modelo Groq levanta `GroqError` e a
> CLI não inicia, mesmo com `API_SELECT=openrouter`.

### Memória de sessão

O agente é criado com um **checkpointer** do LangGraph:

```python
from langgraph.checkpoint.memory import InMemorySaver

checkpointer = InMemorySaver()
```

Ele é passado em `create_agent(checkpointer=...)` e ativado no `invoke` pela
configuração de thread:

```python
config = {"configurable": {"thread_id": "default"}}
```

Consequências:

- cada pergunta é enviada **junto com as mensagens anteriores da mesma thread**,
  então follow-ups ("e no mês passado?") funcionam sem código de histórico na CLI;
- o estado fica **em RAM**: encerrar o processo descarta a sessão;
- o `thread_id` é fixo em `"default"`, logo há **uma única sessão** por execução —
  não há como manter duas conversas simultâneas.

### Seleção de modelo

A variável `API_SELECT` (`.env`) determina o provider:

| `API_SELECT`  | Resultado                                                        |
|----------------|------------------------------------------------------------------|
| `groq`         | Groq / `openai/gpt-oss-120b` — sempre                            |
| `openrouter`   | OpenRouter / `qwen/qwen3-30b-a3b-instruct-2507`                  |
| ausente        | Groq se `check_openrouter_key()` falhar; caso contrário, OpenRouter |
| qualquer outro | `UnboundLocalError` — ver [bug conhecido](#seleção-de-modelo)     |

`check_openrouter_key()` chama `GET https://openrouter.ai/api/v1/key` com a
chave do `.env` e devolve `True` apenas em HTTP 200; qualquer
`requests.RequestException` (incluindo timeout de 5 s) devolve `False`.

> **Bug conhecido** — se `API_SELECT` não for `groq` nem `openrouter` **e**
> `check_openrouter_key()` retornar `True`, nenhum `if` casa e `model` nunca é
> atribuído, resultando em `UnboundLocalError`. Na prática só aparece com um
> valor inesperado em `API_SELECT`; a correção é um `else` explícito.

| Item               | Valor atual                                          |
|--------------------|------------------------------------------------------|
| Framework          | LangChain (`create_agent`)                           |
| Provider 1         | Groq (`init_chat_model`, `model_provider`)          |
| Modelo 1           | `openai/gpt-oss-120b`                                |
| Provider 2         | OpenRouter (`init_chat_model`)                       |
| Modelo 2           | `qwen/qwen3-30b-a3b-instruct-2507`                   |
| `temperature`      | `0.1` (respostas determinísticas)                    |
| `timeout`          | `60000` **milissegundos** (60 s)                     |
| `max_tokens`       | `7000` (Groq) / `10000` (OpenRouter)                 |
| Ferramentas        | `create_json`, `lista_arquivos`                      |
| Memória            | `InMemorySaver` (LangGraph), `thread_id="default"`   |
| Prompt de sistema  | `system_base.md` + `specific_role.md`                |

### Interface (CLI)

`src/nlq/main.py` monta o loop de conversa com `rich`: `Console.rule()` separa os
turnos, `Prompt.ask("\n[bold cyan]User[/bold cyan]")` lê a pergunta e
`Live(Spinner("dots"), transient=True)` cobre a chamada ao agente. A resposta —
`result["messages"][-1].content` — é impressa como `Panel(Markdown(response),
title="[bold black]Chat[/bold black]")`.

```python
config = {"configurable": {"thread_id": "default"}}

result = agent.invoke(
    {"messages": [{"role": "user", "content": user_input}]},
    config=config,
)
```

O `config` é o que ativa o checkpointer: sem ele a invoke roda sem memória. A
interface não monta histórico manualmente — o LangGraph reconstrói a partir do
estado salvo. `"sair"`, `"exit"` e `"quit"` encerram o loop.

## 3. Configuração do modelo

Trocar de LLM não exige alterar o núcleo — basta editar as chamadas em
`create_nlq_agent()`. Cada provider tem sua própria forma de inicialização:

- **OpenRouter** — `init_chat_model("openrouter:<modelo>")`, com o provider no
  prefixo da string.
- **Groq** — `init_chat_model("<modelo>", model_provider="groq")`, com o provider
  em `model_provider`.

Parâmetros relevantes:

- **`temperature`** — manter baixa (0–0.2): o foco é fidelidade, não criatividade.
- **`max_tokens`** — limita o tamanho da resposta.
- **`timeout`** — em **milissegundos** (ver armadilhas).

### Variáveis de ambiente

| Variável             | Efeito                                                          |
|----------------------|-----------------------------------------------------------------|
| `OPENROUTER_API_KEY` | Chave usada por `check_openrouter_key()` e pelo provider OpenRouter |
| `GROQ_API_KEY`       | Chave do provider Groq — **obrigatória**, mesmo usando OpenRouter |
| `API_SELECT`         | Força o provider (`groq` / `openrouter`); vazio = autodetecção    |


## 4. Tool de planilha

Definida em `src/nlq/tools/extract.py` e registrada em `tools=[create_json,
lista_arquivos]`. É o único caminho de **leitura** dos dados; a outra tool
(`lista_arquivos`, ver §5) apenas informa quais planilhas existem.

```
LLM → create_json → parser (CSV | XLSX) → JSON → LLM
```

```python
@tool
def create_json(name: str, ext: str) -> str
```

- `name` — nome do arquivo sem extensão, por exemplo `academia`.
- `ext` — extensão, por exemplo `csv` ou `xlsx`.
- Resolve `sheets/<ext>/<name>.<ext>` a partir da raiz do pacote.
- `ext` fora de `csv`/`xlsx` levanta `ValueError("Extensão não suportada")`.
- Devolve o **JSON da planilha inteira**, com `ensure_ascii=False`, `indent=2` e
  `default=str` (datas e tipos do `openpyxl` viram string).

### Leitura de CSV

```python
encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]

for encoding in encodings:
    try:
        with path.open("r", encoding=encoding) as arquivo:
            return list(csv.DictReader(arquivo))
    except UnicodeDecodeError:
        continue

raise ValueError("Não foi possível ler o arquivo")
```

O fallback por codificação resolve arquivos em `latin-1`/`cp1252` e também o BOM
UTF-8 dos CSVs de `sheets/csv/` (tratado por `utf-8-sig`, primeira opção da
lista).

### Leitura de XLSX

Trecho simplificado de `read_excel()`:

```python
wb = load_workbook(path, read_only=True, data_only=True)

for sheet in wb.worksheets:
    rows = sheet.iter_rows(values_only=True)
    headers = next(rows)          # StopIteration → aba vazia vira []
    data[sheet.title] = [dict(zip(headers, row)) for row in rows]
```

- `read_only=True` mantém o custo baixo para arquivos grandes; `data_only=True`
  entrega o **valor em cache** da fórmula, não a fórmula.
- O retorno é um **dict por aba**: `{nome_da_aba: [linhas]}`. Arquivo com uma aba
  só não muda esse formato — o LLM sempre recebe o mapa de abas.
- Aba sem linhas (cabeçalho ausente) devolve `[]`.

Requisitos ainda **não atendidos** pela implementação atual:

- Ausência de dado (`n/a`, célula vazia) não é sinalizada explicitamente — a tool
  devolve o dict cru.
- Falha de leitura não é explicada: erros como `FileNotFoundError` e
  `UnicodeDecodeError` sobem direto para o LLM, sem tratamento.
- Não é agnóstica de layout no acesso a disco: `ext` funciona ao mesmo tempo como
  extensão **e** como nome da pasta em `sheets/`.
- O XLSX semi-estruturado é lido de forma bruta: células mescladas viram `None`,
  cabeçalho multinível vira coluna do primeiro nível, múltiplos blocos na mesma
  aba viram uma tabela só (detalhes em [`architecture.md`](architecture.md) §5).
- `indent=2` infla o payload — em arquivo multi-aba o JSON pode se aproximar do
  `max_tokens`.

## 5. Tool de descoberta

Definida em `src/nlq/tools/listar_planilhas.py`:

```python
@tool
def lista_arquivos() -> list[str]
```

- Não recebe argumentos — lê `sheets/csv/` e `sheets/xlsx/` e concatena as duas
  listas.
- Devolve os **nomes com extensão** (`academia.csv`,
  `MATRIZ ENCAMINHADA - FINAL.xlsx`), porque é assim que o LLM precisa chamá-la em
  `create_json`.
- Remove o trecho entre parênteses do nome com `re.sub(r"\([^)]*\)", "", ...)`.
- É o que permite ao agente responder "quais planilhas você tem?" sem adivinhar
  nomes — resolver isso por tentativa-e-erro consumiria contexto à toa.

Limitações: `listar_csvs()` e `listar_xlsx()` são implementações duplicadas, não
filtram por extensão (`iterdir()` devolve qualquer arquivo da pasta) e não tratam
pasta inexistente.

## 6. Prompt de sistema

Montado por concatenação de dois arquivos Markdown em
`src/nlq/agent/prompts/`, lidos por `load_prompt()`:

- `system_base.md` — regras de funcionamento do agente. Tem três blocos:
  regras gerais (uso das ferramentas, nunca inventar resultado, explicar erro),
  estado e continuidade (reaproveitar análise anterior, não reiniciar fluxo) e
  *sobre mostrar planilha* (exibir **todas** as abas, linhas e colunas, sem
  resumir nem selecionar exemplos).
- `specific_role.md` — **opcional**, define o escopo (papel, competência e base
  normativa). Vem com um exemplo de domínio e pode ser editado ou substituído
  livremente pelo usuário; o núcleo não depende do seu conteúdo.

O bloco de continuidade e o de exibição completa dependem da memória de sessão e
do retorno multi-aba: são o que permite seguir um fluxo entre turnos e receber a
planilha inteira do XLSX.

Os nomes são string hardcoded na chamada em `create_nlq_agent()`: renomear um
arquivo exige atualizar essa referência, ou `load_prompt()` levanta
`FileNotFoundError` no startup.

## 7. Dívidas técnicas conhecidas

### Payload e contexto

- **`indent=2` no JSON** aumenta o payload; XLSX multi-aba pode se aproximar do
  `max_tokens` (7000 Groq / 10000 OpenRouter).
- **Ausência de dado não sinalizada** pela tool (ver §4).
- **Falha de leitura sem tratamento** — erros sobem crus para o LLM (ver §4).

### Parser XLSX

- **Níveis 3 e 4 lidos de forma bruta** — `dict(zip(headers, row))` na primeira
  linha: mescladas viram `None`, cabeçalho multinível vira coluna do primeiro
  nível, com `data_only=True` fórmula sem cache devolve `None`, múltiplos blocos
  na mesma aba viram uma tabela só e abas ocultas também são lidas.
- `read_only=True` percorre as linhas sem materializar tudo em memória, mas o JSON
  final é montado inteiro — o limite real continua sendo o contexto do LLM.

### Sessão e memória

- **Memória volátil** — `InMemorySaver` é em RAM; encerrar o processo perde a
  sessão.
- **`thread_id` fixo em `"default"`** — uma sessão por execução, sem separação de
  conversas nem concorrência.

### Acesso a disco

- **Path sem validação** — `name` e `ext` não são sanitizados, então `../../.env`
  escapa de `sheets/`.
- **`ext` acoplado ao layout** — a extensão também nomeia a pasta em `sheets/`.
- **`lista_arquivos` duplicado e sem guardas** (ver §5).

### Agente e configuração

- **Construção incondicional dos dois modelos** — exige `GROQ_API_KEY` mesmo
  usando OpenRouter.
- `model` pode ficar sem atribuição quando `API_SELECT` é inesperado e a chave do
  OpenRouter é válida (ver [bug conhecido](#seleção-de-modelo)).
- `requests` usado em `agent.py` sem estar declarado em `pyproject.toml`.
- `check_openrouter_key()` faz uma chamada de rede a cada criação do agente
  (inclusive já coberta pela autodetecção, quando `API_SELECT` está vazio).
- Sem testes automatizados.

## 8. Evoluções possíveis

A próxima evolução prioriza diminuir o contexto enviado ao modelo:

1. execução tabular local (Pandas ou executor equivalente) para filtros,
   agregações e ordenações;
2. busca semântica/RAG para recuperar registros textualmente relacionados;
3. combinação dos dois para perguntas híbridas.

AST fica reservada para quando a complexidade das operações justificar uma
representação intermediária própria. NL2SQL não é prioridade para planilhas
genéricas; é considerado principalmente para fontes relacionais reais ou dados
com relações claramente identificáveis.

Detalhes em [`possible_implements.md`](possible_implements.md).
