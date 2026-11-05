# Agente

## 1. Papel

O agente é a camada de raciocínio e orquestração do NLQ. Ele recebe a pergunta em
linguagem natural, **consulta as planilhas através de ferramentas** e devolve uma
resposta fiel e rastreável. Também **mantém o histórico da sessão** em memória,
de modo que um turno pode retomar o contexto do anterior.

O LLM é quem decide o que consultar, interpreta os resultados e redige a
resposta — não há etapas rigidamente separadas no código.

## 2. Implementação atual

Definido em `create_nlq_agent()` — `src/nlq/agent/agent.py`. Usa
`langchain.agents.create_agent`, com `InMemorySaver` e middleware próprio. Há
**dois provedores candidatos** e a escolha acontece em tempo de execução, com
logs de inicialização:

> `NLQ_MODEL` sobrepõe o modelo escolhido. `NLQ_SESSION_ID` e
> `NLQ_PIN_PROVIDER`/`NLQ_PROVIDER` controlam roteamento e cache no OpenRouter.
> `NLQ_REASONING` controla o canal de raciocínio.

A função devolve uma **tupla `(agente, checkpointer)`**. Os dois consumidores
desempacotam o retorno: `main.py` (CLI) e `api.py` (API FastAPI) — este último
precisa do checkpointer para `DELETE /api/limpar-conversa` apagar a thread.

### Memória de sessão

O agente é criado com um **checkpointer** do LangGraph:

```python
from langgraph.checkpoint.memory import InMemorySaver

checkpointer = InMemorySaver()
```

Ele é passado em `create_agent(checkpointer=...)` e ativado pela configuração de
thread em cada execução:

```python
config = {"configurable": {"thread_id": "default"}}
```

Consequências:

- cada pergunta é enviada **junto com as mensagens anteriores da mesma thread**,
  então follow-ups ("e no mês passado?") funcionam sem código de histórico na
  CLI;
- o estado fica **em RAM**: encerrar o processo descarta a sessão;
- a **CLI** usa `thread_id="default"` (uma sessão por execução); a **API** aceita
  `thread_id` por requisição, permitindo várias conversas no mesmo processo;
- o mesmo checkpointer é usado por CLI e API, e `DELETE /api/limpar-conversa`
  chama `checkpointer.delete_thread(thread_id)` para apagar a thread informada.

### Seleção de modelo

A decisão é `usar_groq = (API_SELECT == "groq" or not check_openrouter_key())`.
Em caso positivo usa Groq; senão OpenRouter. São emitidos logs `[MODELO]` na
inicialização. Se `NLQ_MODEL` estiver definido, ele tem prioridade (aceita o
prefixo `openrouter:`).

`check_openrouter_key()` chama `GET https://openrouter.ai/api/v1/key` com a chave
do `.env` e devolve `True` apenas em HTTP 200; qualquer `requests.RequestException`
devolve `False`.

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
| Prompt de sistema  | `system_base.md` + `specific_role.md`                |
| Skills             | pasta `skills/` (metadados no disco; roteamento pelas descrições das ferramentas) |
| Override de modelo | `NLQ_MODEL`                                          |
| Cache/roteamento   | `NLQ_SESSION_ID`, `NLQ_PIN_PROVIDER`, `NLQ_PROVIDER` |
| Raciocínio         | `NLQ_REASONING` (`separate` padrão / `exclude` / `off`) |
| Limites            | `NLQ_MAX_ROWS` (500), `NLQ_ROWS_DEFAULT` (20), `NLQ_TOOL_CALL_LIMIT` (25) |
| Poda de contexto   | `NLQ_CONTEXT_TRIGGER_TOKENS` (25000), `NLQ_CONTEXT_KEEP_TOOL_RESULTS` (5) |

### Middleware

- **`CacheDeChamadas`** — quando o modelo repete a mesma ferramenta com os mesmos
  argumentos, devolve o resultado já obtido (TTL de 300 s, até 256 entradas) com
  o aviso `[REPETIDO]`, em vez de executar de novo.
- **`ContextEditingMiddleware`** — aplica `ClearToolUsesEdit`: acima de
  `NLQ_CONTEXT_TRIGGER_TOKENS` (padrão 25000, contagem aproximada), os resultados
  de ferramenta mais antigos viram `[cleared]` **apenas na mensagem enviada ao
  modelo**, preservando os `NLQ_CONTEXT_KEEP_TOOL_RESULTS` (padrão 5) mais
  recentes. O checkpointer mantém o histórico completo.
- **`ToolCallLimitMiddleware`** — teto de `NLQ_TOOL_CALL_LIMIT` (padrão 25)
  chamadas por execução, com `exit_behavior="continue"` (o modelo finaliza com o
  que já tem em vez de travar).
- **`TratarErroDeTool`** — converte exceções de ferramenta em `ToolMessage` de
  status `error`, orientando o modelo a corrigir os argumentos e tentar de novo.

### Desempenho (otimizações)

O gargalo de tempo é o **LLM** (tokens de entrada e número de chamadas), não o
Pandas. Medidas aplicadas:

- **Prompt enxuto** — regras de roteamento/economia consolidadas em
  `system_base.md` e descrições de ferramentas reduzidas.
- **Cache de prompt** — `session_id` estável (`NLQ_SESSION_ID` ou um id por
  processo) faz o OpenRouter usar roteamento fixo, aumentando `cache_read` entre
  as chamadas. `NLQ_PIN_PROVIDER`/`NLQ_PROVIDER` opcionalmente fixam o provedor.
- **Saída limitada** — `NLQ_MAX_TOKENS` (padrão `5000`) evita respostas que
  estouram o teto.
- **Anti-loop** — `CacheDeChamadas` devolve resultados repetidos e
  `ToolCallLimitMiddleware` impede exploração sem limites.
- **Poda de contexto** — `ContextEditingMiddleware` reduz o histórico enviado
  quando ele cresce.
- **Warm-up** — schema/registros (e índice semântico) carregados em segundo
  plano (`nlq/warmup.py`).
- **Métricas** — `PerfCallbackHandler` (`agent/metrics.py`) mede duração, tokens
  (entrada/saída/cache) e caracteres por ferramenta; a CLI o ativa por turno.

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
| `/api/chat`            | POST   | Streaming NDJSON. Corpo `{"message": str, "thread_id": str}`. Eventos: `status` (processando/executando ferramenta/consultando modelo), `token` (texto parcial, coalescido em lotes de ~24 chars), `thinking` (raciocínio em canal separado), `result` (`response`, `planilha`), `error`, `ping`. Usa fila + keep-alive (10s) + cancelamento cooperativo. |
| `/api/limpar-conversa` | DELETE | Corpo `{"thread_id": str}`. Cancela eventual consulta e apaga o checkpoint e os anexos da conversa. |
| `/api/limpar-cache`    | DELETE | Sem corpo. Bloqueia se houver qualquer consulta ativa (`409`). Senão `limpar_cache_dataframes()` + `limpar_indices(disco=True)`; devolve `{status, dataframes_ram, indice_ram, consulta_ram, arquivos_disco, bytes_disco}`. |

As rotas de API são registradas **antes** do mount estático em `/`, então
`/health`, `/api/*` e `/docs` têm precedência sobre o frontend.

`/api/chat` monta `config={"configurable":{"thread_id": request.thread_id}}` e
invoca o agente via `agente.stream` com `stream_mode=["messages","values"]` em
thread separada, publicando eventos em fila; apenas tokens de `AIMessageChunk`
do modelo viram eventos `token` (mensagens de ferramenta e argumentos de
tool-call são ignorados). O raciocínio (`reasoning_content`) vira eventos
`thinking`. O campo `planilha` em `result` é extraído via `_ultima_planilha()`
(última chamada `create_json`). API e CLI compartilham o mesmo checkpointer.

### Interface (Desktop)

`src/nlq/desktop.py` é o ponto de entrada do executável empacotado: sobe a API em
`127.0.0.1`, escolhe uma porta livre a partir de `8000` e abre o navegador. Os
caminhos de recursos (frontend, prompts, skills, `sheets/`, `.env`) são
resolvidos por `src/nlq/paths.py` para funcionar tanto no repositório quanto
empacotado.

## 3. Configuração do modelo

Trocar de LLM não exige alterar o núcleo — basta editar as chamadas em
`create_nlq_agent()` (ou definir `NLQ_MODEL`). Cada provider tem sua própria
forma de inicialização:

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

| Variável                       | Efeito                                                          |
|--------------------------------|-----------------------------------------------------------------|
| `OPENROUTER_API_KEY`           | Chave usada por `check_openrouter_key()` e pelo provider OpenRouter |
| `GROQ_API_KEY`                 | Chave do provider Groq (usada quando selecionado)                 |
| `OPENAI_API_KEY`               | Usada pela busca semântica (embeddings `text-embedding-3-small`)  |
| `API_SELECT`                   | Força o provider (`groq` / `openrouter`); vazio = autodetecção    |
| `NLQ_MODEL`                    | Sobrepõe o modelo escolhido (aceita `openrouter:`)                |
| `NLQ_MAX_TOKENS`               | Teto de tokens de resposta (padrão 5000)                          |
| `NLQ_SESSION_ID`               | `session_id` estável para cache de prompt no OpenRouter           |
| `NLQ_PIN_PROVIDER` / `NLQ_PROVIDER` | Fixa o provedor no OpenRouter (padrão DeepSeek)              |
| `NLQ_REASONING`                | `separate` (padrão) / `exclude` / `off`                           |
| `NLQ_CONTEXT_TRIGGER_TOKENS`   | Gatilho de poda de contexto (padrão 25000)                        |
| `NLQ_CONTEXT_KEEP_TOOL_RESULTS`| Resultados recentes nunca podados (padrão 5)                      |
| `NLQ_TOOL_CALL_LIMIT`          | Teto de chamadas de ferramenta por execução (padrão 25)           |
| `NLQ_MAX_ROWS` / `NLQ_ROWS_DEFAULT` | Teto e padrão de linhas/grupos em `consultar_dados`          |

## 4. Tools de planilha/dados

### `consultar_dados` (consultar_dados.py)
Executor tabular com Pandas. A LLM **não gera nem executa código**: informa uma
operação e parâmetros validados contra as colunas reais da planilha (sem
`eval`/`exec`).

- Operações: `contar`, `filtrar`, `agregar`, `agrupar`, `ordenar`, `metas`,
  `distintos`.
- Filtros: lista de `{coluna, operador, valor}` combinados por AND. Operadores:
  `igual`, `diferente`, `maior`, `maior_igual`, `menor`, `menor_igual`,
  `contem`, `nao_contem`, `vazio`, `nao_vazio`, `em`.
- Agregações: `contagem`, `soma`, `media`, `minimo`, `maximo`; em `agrupar`
  também `valores` (valores distintos por grupo, com `_refs`).
- **Integridade**: `n/a`, célula vazia, traço e "não se aplica" contam como
  **ausência**, nunca como zero; agregações reportam quantos valores foram
  ignorados por não serem numéricos. Números no formato brasileiro
  (`1.234,56`, `R$`) são reconhecidos.
- **Referências do RAG**: `refs` (`[{"aba","indice"}]`) restringe a consulta aos
  candidatos retornados por `buscar_semantico`, sem duplicação; uma lista
  explícita vazia não significa "tudo".
- Resultados compactos, com projeção de colunas e `_origem` (aba/índice).
  Limites: `limite` por consulta (padrão 20, teto `NLQ_MAX_ROWS` = 500),
  sinalizado por `truncado`.
- Cache de DataFrames por arquivo (`_DF_CACHE`, até 8 entradas, invalidado por
  mtime/tamanho).

### `create_json` (extract.py)
Extrai registros completos quando estritamente necessário.

- Valida extensão (`csv`/`xlsx`), resolve em `data_dir()/<ext>/<name>.<ext>` e
  checa se o arquivo existe.
- Usa `load_records()` (loader com cache). CSV: lista de dicts. XLSX: dict por
  aba (guiado por schema).
- **Guarda por tamanho**: se o JSON resultante exceder 20.000 caracteres,
  devolve `EXTRACAO_BLOQUEADA_POR_TAMANHO` orientando uso de `buscar_semantico`
  ou consulta estruturada, sem enviar os registros.
- Retorno com `ensure_ascii=False`, `indent=2`, `default=str`. Logs
  `[TOOL] create_json inicio` e `[PERF] tool=create_json ...` (try/finally).

### `buscar_semantico` (retrieval.py)
RAG com embeddings (OpenAI `text-embedding-3-small`). Retorna registros mais
relevantes (com aba, índice e similaridade) e a referência pronta para
`consultar_dados`. Orçamento de ~6.000 caracteres por resposta e 1.500 por
registro; `top_k` ajustado para a faixa 1–20. Cache de índice por fingerprint
(mtime/tamanho), em RAM e em disco.

### `consultar_schema` (schema_info.py)
Retorna estrutura (abas, regiões tabulares, linha de cabeçalho, limites e nomes
de colunas) **sem ler registros** (usa `xldetect` + normalização). Para CSV não
há schema estrutural — a resposta informa isso. Colunas com nome gerado
(`coluna_N`) são sinalizadas.

### Leitura de CSV

```python
encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]

for encoding in encodings:
    try:
        with path.open("r", encoding=encoding, newline="") as arquivo:
            return list(csv.DictReader(arquivo))
    except UnicodeDecodeError:
        continue

raise ValueError("Não foi possível ler o arquivo")
```

O fallback por codificação resolve arquivos em `latin-1`/`cp1252` e também o BOM
UTF-8 dos CSVs (tratado por `utf-8-sig`, primeira opção da lista).

### Leitura de XLSX

Guiada pelo schema do `xldetect` (regiões), com `openpyxl`:

```python
wb = load_workbook(path, read_only=False, data_only=True)
# para cada região detectada: reconstrói mesclagens verticais,
# ignora linhas totalmente vazias e monta dict(zip(headers, values))
```

- `data_only=True` entrega o **valor em cache** da fórmula, não a fórmula.
- O retorno é um **dict por aba**: `{nome_da_aba: [linhas]}`. Uma aba pode ter
  várias regiões, cujos registros são concatenados.
- Aba sem regiões detectadas preserva células não vazias com nomes genéricos
  (`coluna_N`) e emite um aviso.

Requisitos ainda **não atendidos** pelo parser:

- ausência de dado (`n/a`, célula vazia) não é sinalizada explicitamente no
  `create_json`;
- falha de leitura sobe crua para o LLM (mitigada por `TratarErroDeTool`);
- mesclagens horizontais e cabeçalho multinível ainda não são interpretados
  (detalhes em [`architecture.md`](architecture.md) §5);
- `indent=2` infla o payload — mitigado pela guarda de 20.000 caracteres.

## 5. Tool de descoberta

Definida em `src/nlq/tools/listar_planilhas.py`:

```python
@tool
def lista_arquivos() -> list[str]
```

- Não recebe argumentos — lê `sheets/csv/` e `sheets/xlsx/` e concatena as duas
  listas.
- Devolve os **nomes com extensão** (`academia.csv`,
  `MATRIZ ENCAMINHADA - FINAL.xlsx`), porque é assim que o LLM precisa chamá-la
  em `create_json`/`consultar_dados`/`buscar_semantico`.
- Remove o trecho entre parênteses do nome com `re.sub(r"\([^)]*\)", "", ...)`.
- É o que permite ao agente responder "quais planilhas você tem?" sem adivinhar
  nomes — resolver isso por tentativa-e-erro consumiria contexto à toa.

Limitações: `listar_csvs()` e `listar_xlsx()` são implementações duplicadas, não
filtram por extensão (`iterdir()` devolve qualquer arquivo da pasta) e não tratam
pasta inexistente.

### `goat` (dev_master.py)

Ferramenta de easter egg que devolve uma descrição aleatória "explicando por que
Gabriel é o GOAT". Não faz parte das tools de planilha.

## 6. Prompt de sistema

Montado por concatenação de arquivos Markdown em `src/nlq/agent/prompts/`:

- `system_base.md` — regras de funcionamento do agente: uso das ferramentas,
  fidelidade, continuidade da conversa, **economia de etapas** (planejar,
  paralelizar, não repetir consultas, não fazer rodadas de conferência),
  **roteamento por objetivo** (schema × dados × semântica × arquivos ×
  extração), integridade dos dados e resposta concisa sem passos intermediários.
- `specific_role.md` — define o escopo do domínio (papel, competência, base
  normativa). Vem com um exemplo e pode ser editado livremente; o núcleo não
  depende do seu conteúdo.

O prompt completo (`system_base.md` + `\n\n` + `specific_role.md`) é passado a
`create_agent`. Os `SKILL.md` permanecem no disco como metadados (validados na
inicialização); o roteamento é dado pelas descrições das próprias ferramentas e
pelas regras do prompt.

## 7. Dívidas técnicas conhecidas

### Payload e contexto

- **`indent=2` no JSON** aumenta o payload; XLSX multi-aba pode se aproximar do
  `max_tokens` (`NLQ_MAX_TOKENS`, padrão `5000`).
- **Ausência de dado não sinalizada** pelo `create_json` (existe em
  `consultar_dados`).
- **Falha de leitura sem tratamento específico** — erros sobem para o LLM
  (convertidos em `ToolMessage` de erro por `TratarErroDeTool`).

### Parser XLSX

- Regiões detectadas e mesclagens verticais reconstruídas; ainda não tratados:
  mesclagens horizontais, cabeçalho multinível, fórmula sem cache
  (`data_only=True` devolve `None`) e abas ocultas.
- `read_only=False` materializa o workbook; o limite real de payload continua
  sendo o contexto do LLM.

### Sessão e memória

- **Memória volátil** — `InMemorySaver` é em RAM; encerrar o processo perde a
  sessão.
- **Sem persistência entre processos** — o `thread_id` da API existe só em
  memória.

### Acesso a disco

- **Path com validação** — `buscar_semantico`/`consultar_schema` validam
  `is_relative_to(sheets_dir)`; `create_json`/`consultar_dados` resolvem sob
  `data_dir()/<ext>/` e checam `is_file()`.
- **`ext` acoplado ao layout** — a extensão também nomeia a pasta em `sheets/`.
- **`lista_arquivos`** — sem filtro por extensão nem tratamento de pasta ausente.

### Agente e configuração

- **Seleção simplificada** — `usar_groq` evita construção ambígua; logs
  `[MODELO]`.
- `requests` usado em `agent.py`.
- `check_openrouter_key()` faz uma chamada de rede para autodetecção (timeout 5s).
- **Skills** — validadas na inicialização (RuntimeError se nenhuma SKILL.md).
- **Testes** — há suíte `unittest` em `tests/` (tools, caches, cancelamento,
  contexto, métricas, paths, desktop).

## 8. Evoluções possíveis

A prioridade é diminuir ainda mais o contexto enviado ao modelo e aumentar a
confiabilidade:

1. aprimorar a busca semântica/RAG (seleção/filtros por aba e uso de `refs`);
2. melhorar o parser para mesclagens horizontais e cabeçalhos multinível;
3. validação determinística da resposta antes de devolvê-la ao usuário;
4. persistência de sessão (checkpointer em disco).

AST fica reservado para quando a complexidade das operações justificar uma
representação intermediária própria. NL2SQL não é prioridade para planilhas
genéricas; é considerado principalmente para fontes relacionais reais.

Detalhes em [`possible_implements.md`](possible_implements.md).
