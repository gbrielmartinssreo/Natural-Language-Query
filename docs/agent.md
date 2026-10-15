# Agente

## 1. Papel

O agente é a camada de raciocínio e orquestração do NLQ. Ele recebe a pergunta em
linguagem natural, **consulta a planilha através de uma ferramenta** e devolve uma
resposta fiel e rastreável. Também **mantém o histórico da sessão** em memória,
de modo que um turno pode retomar o contexto do anterior.

O LLM é quem decide o que consultar, interpreta o JSON retornado e redige a
resposta — não há etapas rigidamente separadas no código.

## 2. Implementação atual

Definido em `create_nlq_agent()` — `src/nlq/agent/agent.py`. Usa `langchain.agents.create_agent`, com `InMemorySaver` e middleware próprio. Há **dois provedores candidatos** e a escolha acontece em tempo de execução com logs de inicialização:

```python
checkpointer = InMemorySaver()
max_tokens = int(os.getenv("NLQ_MAX_TOKENS", "5000"))

model_openrouter = init_chat_model(
    "openrouter:deepseek/deepseek-v4-flash-0731",
    temperature=0.1,
    timeout=60000,
    max_tokens=max_tokens,
    session_id=...,                 # roteamento fixo p/ cache de prompt
    # raciocínio separado por padrão (NLQ_REASONING=separate):
    # vai para additional_kwargs["reasoning_content"] e NÃO polui o content
)

model_groq = init_chat_model(
    "openai/gpt-oss-120b",
    model_provider="groq",
    temperature=0.1,
    timeout=60,
    max_tokens=max_tokens,
)

if os.getenv("API_SELECT") == "groq" or not check_openrouter_key():
    model = model_groq
else:
    model = model_openrouter

tools = [
    create_json, goat, lista_arquivos,
    consultar_schema, buscar_semantico, consultar_dados,
]

agent = create_agent(
    model=model,
    tools=tools,
    checkpointer=checkpointer,
    system_prompt=(
        load_prompt("system_base.md")
        + "\n\n" + load_prompt("specific_role.md")
        + "\n\n" + REGRAS_DE_CONSULTA
    ),
    middleware=[
        CacheDeChamadas(),
        ToolCallLimitMiddleware(run_limit=10, exit_behavior="continue"),
        TratarErroDeTool(),
    ],
)

return agent, checkpointer
```

> A variável `NLQ_MODEL` sobrepõe o modelo escolhido. `NLQ_SESSION_ID` e
> `NLQ_PIN_PROVIDER`/`NLQ_PROVIDER` controlam roteamento e cache no OpenRouter.

A função devolve uma **tupla `(agente, checkpointer)`**. Os dois consumidores
desempacotam o retorno: `main.py` (CLI) e `api.py` (API FastAPI) — este último
precisa do checkpointer para `DELETE /api/limpar-conversa` apagar a thread.

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
  não há como manter duas conversas simultâneas;
- o mesmo checkpointer é usado pela **API** (`src/nlq/api.py`): CLI e API
  enxergam a mesma thread, e `DELETE /api/limpar-conversa` chama
  `checkpointer.delete_thread("default")` para limpá-la.

### Seleção de modelo

A decisão é feita por `usar_groq = (API_SELECT=='groq' or not check_openrouter_key())`. Em caso positivo usa Groq (`openai/gpt-oss-120b`), senão OpenRouter (`qwen/qwen3-30b-a3b-instruct-2507`). São emitidos logs `[MODELO] ...` na inicialização.

`check_openrouter_key()` chama `GET https://openrouter.ai/api/v1/key` com a chave do `.env` e devolve `True` apenas em HTTP 200; qualquer `requests.RequestException` devolve `False`.

| Item               | Valor atual                                          |
|--------------------|------------------------------------------------------|
| Framework          | `langchain.agents.create_agent` (LangGraph subjacente) |
| Provider 1         | Groq (`init_chat_model`, `model_provider`)          |
| Modelo 1           | `openai/gpt-oss-120b`                                |
| Provider 2         | OpenRouter (`init_chat_model`)                       |
| Modelo 2           | `deepseek/deepseek-v4-flash-0731` (raciocínio em canal separado) |
| `temperature`      | `0.1` (respostas determinísticas)                    |
| `timeout`          | `60` s (Groq) / `60000` ms (OpenRouter) — ~60 s por chamada |
| `max_tokens`       | `5000` (padrão; `NLQ_MAX_TOKENS`)                    |
| Ferramentas        | `create_json`, `goat`, `lista_arquivos`, `consultar_schema`, `buscar_semantico`, `consultar_dados` |
| Middleware         | `CacheDeChamadas`, `ContextEditingMiddleware`, `ToolCallLimitMiddleware(25)`, `TratarErroDeTool` |
| Memória            | `InMemorySaver` (LangGraph)                          |
| Prompt de sistema  | `system_base.md` + `specific_role.md` + `REGRAS_DE_CONSULTA` |
| Skills             | pasta `skills/` (metadados no disco; roteamento pelas descrições das ferramentas) |
| Override de modelo | `NLQ_MODEL`                                          |
| Cache/roteamento   | `NLQ_SESSION_ID`, `NLQ_PIN_PROVIDER`, `NLQ_PROVIDER` |
| Raciocínio         | `NLQ_REASONING` (`separate` padrão / `exclude` / `off`) |
| Limites            | `NLQ_MAX_ROWS` (500), `NLQ_ROWS_DEFAULT` (20), `NLQ_TOOL_CALL_LIMIT` (25) |

### Desempenho (otimizações)

O gargalo de tempo é o **LLM** (tokens de entrada e número de chamadas), não o
Pandas. Medidas aplicadas:

- **Prompt enxuto** — `REGRAS_DE_CONSULTA` consolidado (uma fonte canônica de
  roteamento) e descrições de ferramentas reduzidas; o payload fixo por chamada
  caiu de ~25.900 para ~13.900 caracteres.
- **Cache de prompt** — `session_id` estável faz o OpenRouter usar roteamento
  fixo, aumentando `cache_read` entre as chamadas.
- **Saída limitada** — `NLQ_MAX_TOKENS` (padrão `5000`) evita respostas que
  estouram o teto (antes: uma geração de 10.000 tokens levava ~65 s). Respostas
  que atingem o limite são sinalizadas como interrompidas.
- **Anti-loop** — `CacheDeChamadas` devolve resultados repetidos e
  `ToolCallLimitMiddleware(10)` impede exploração sem limites.
- **Warm-up** — esquema/registros (e índice semântico) carregados em segundo
  plano (`nlq/warmup.py`).


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

### Interface (API)

`src/nlq/api.py` cria o FastAPI `app` e o agente no **import do módulo**
(`agent, checkpointer = create_nlq_agent()`), com o entrypoint declarado no
`pyproject.toml`:

```toml
[tool.fastapi]
entrypoint = "nlq.api:app"
```

Execução: `uv run fastapi dev` (desenvolvimento) ou `uv run fastapi run`
(produção) — a `fastapi[standard]` resolve o servidor (Uvicorn) e a documentação
em `/docs`.

| Rota                   | Método | Comportamento                                                        |
|------------------------|--------|----------------------------------------------------------------------|
| `/`                    | GET    | Serve o frontend estático (`frontend/index.html` — `StaticFiles(html=True)`) |
| `/health`              | GET    | `{"status": "ok"}`                                                   |
| `/api/chat`            | POST   | Streaming NDJSON. Corpo `{"message": str, "thread_id": str}`. Eventos: `status` (processando/executando ferramenta/consultando modelo), `token` (texto parcial do modelo, coalescido em lotes), `result` (`response`, `planilha`), `error`, `ping`. Usa fila + keep-alive (10s) + cancelamento cooperativo. |
| `/api/limpar-conversa` | DELETE | Corpo `{"thread_id": str}`. Bloqueia se consulta ativa para thread (`409`). Senão `checkpointer.delete_thread(thread_id)`. |

As rotas de API são registradas **antes** do mount estático em `/`, então
`/health`, `/api/*` e `/docs` têm precedência sobre o frontend.

`/api/chat` monta `config={"configurable":{"thread_id": request.thread_id}}` e invoca agente via `agente.stream` com `stream_mode=["messages","values"]` em thread separada, publicando eventos em fila; apenas tokens de `AIMessageChunk` do modelo viram eventos `token` (mensagens de ferramenta e argumentos de tool-call são ignorados). O campo `planilha` em `result` é extraído via `_ultima_planilha()` (última chamada `create_json`). API e CLI compartilham o mesmo checkpointer (mesma memória entre execuções no mesmo processo).

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
- **`timeout`** — a unidade depende da integração: `langchain-groq` usa
  **segundos** (repassado ao SDK Groq / httpx), `langchain-openrouter` usa
  **milissegundos** (`timeout_ms` no SDK). Ambos configurados para ~60 s por
  chamada ao modelo — não para a execução inteira do agente.

### Variáveis de ambiente

| Variável             | Efeito                                                          |
|----------------------|-----------------------------------------------------------------|
| `OPENROUTER_API_KEY` | Chave usada por `check_openrouter_key()` e pelo provider OpenRouter |
| `GROQ_API_KEY`       | Chave do provider Groq (usada quando selecionado)                 |
| `OPENAI_API_KEY`     | Usada pela busca semântica (embeddings `text-embedding-3-small`)  |
| `API_SELECT`         | Força o provider (`groq` / `openrouter`); vazio = autodetecção    |


## 4. Tools de planilha/dados

### `create_json` (extract.py)
Extrai registros completos quando estritamente necessário. Registrada entre as tools.

- Valida extensão (`csv`/`xlsx`), resolve em `data_dir()/ext/<name>.<ext>`, checa arquivo existe.
- Usa `load_records()` (loader com cache). CSV: lista de dicts. XLSX: dict por aba (guiado por schema).
- **Guarda por tamanho**: se JSON resultante > 20.000 caracteres, retorna mensagem `EXTRACAO_BLOQUEADA_POR_TAMANHO` orientando uso de `buscar_semantico`, sem repetir extração completa.
- Retorno com `ensure_ascii=False`, `indent=2`, `default=str`. Logs `[TOOL] create_json inicio` e `[PERF] tool=create_json ...` (try/finally).

### `buscar_semantico` (retrieval.py)
RAG com embeddings (OpenAI `text-embedding-3-small`). Retorna registros mais relevantes (com aba/origem e similaridade). Cache de índice por fingerprint (mtime/tamanho). Logs perf. `top_k` 1–20.

### `consultar_schema` (schema_info.py)
Retorna estrutura (abas, regiões, cabeçalhos, colunas) **sem ler registros** (usa `xldetect` + normalização). Útil para perguntas estruturais.

### `lista_arquivos` (listar_planilhas.py)
Descobre planilhas em `sheets/csv/` e `sheets/xlsx/` (nomes com extensão).

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
  `max_tokens`. **Guarda ativa:** `create_json` bloqueia extração acima de 20.000 caracteres e retorna mensagem orientando a usar `buscar_semantico` (não repete extração completa).

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

Montado por concatenação de arquivos Markdown em `src/nlq/agent/prompts/` mais regras embutidas:

- `system_base.md` — regras de funcionamento do agente (uso de ferramentas, fidelidade, continuidade).
- `specific_role.md` — define escopo do domínio (pode ser editado livremente).
- `REGRAS_DE_CONSULTA` (constante em `agent.py`) — política operacional concisa: economia de etapas (planejar, paralelizar, não repetir consultas, não fazer rodadas de conferência), roteamento por objetivo (schema × dados × semântica × arquivos × extração), integridade/consolidação dos dados e resposta concisa sem passos intermediários.

O prompt completo é passado a `create_agent`. Os `SKILL.md` permanecem no disco como metadados, mas o roteamento é dado pelas descrições das próprias ferramentas.

## 7. Dívidas técnicas conhecidas

### Payload e contexto

- **`indent=2` no JSON** aumenta o payload; XLSX multi-aba pode se aproximar do
  `max_tokens` (`NLQ_MAX_TOKENS`, padrão `5000`).
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

- **Path com validação** — `buscar_semantico` e `consultar_schema` validam `is_relative_to(sheets_dir)`. `create_json` resolve sob `data_dir()/ext/` e checa `is_file()`.
- **`ext` acoplado ao layout** — a extensão também nomeia a pasta em `sheets/`.
- **`lista_arquivos`** — lê pastas CSV/XLSX (pode evoluir com filtragem por extensão e tratamento de pasta ausente).

### Agente e configuração

- **Seleção simplificada** — `usar_groq` evita construção ambígua; logs de inicialização `[MODELO]`.
- `requests` usado em `agent.py`.
- `check_openrouter_key()` faz uma chamada de rede para autodetecção (timeout 5s).
- **Skills** — validadas na inicialização (RuntimeError se nenhuma SKILL.md). Carregadas via `FilesystemBackend` do deepagents.
- Sem testes automatizados.

## 8. Evoluções possíveis

A próxima evolução prioriza diminuir o contexto enviado ao modelo:

1. execução tabular local (Pandas ou executor equivalente) para filtros,
   agregações e ordenações;
2. aprimorar busca semântica/RAG (já implementada) com melhor seleção/filtros por aba;
3. combinação dos dois para perguntas híbridas.

AST fica reservada para quando a complexidade das operações justificar uma
representação intermediária própria. NL2SQL não é prioridade para planilhas
genéricas; é considerado principalmente para fontes relacionais reais ou dados
com relações claramente identificáveis.

Detalhes em [`possible_implements.md`](possible_implements.md).
