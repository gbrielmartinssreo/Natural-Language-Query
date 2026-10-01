# Agente

## 1. Papel

O agente é a camada de raciocínio e orquestração do NLQ. Ele recebe a pergunta em
linguagem natural, **consulta a planilha através de uma ferramenta** e devolve uma
resposta fiel e rastreável.

O LLM é quem decide o que consultar, interpreta o JSON retornado e redige a
resposta — não há etapas rigidamente separadas no código.

## 2. Implementação atual

Definido em `create_nlq_agent()` — `src/nlq/agent/agent.py`. Há **dois modelos
candidatos**, e a escolha acontece em tempo de execução:

```python
model1 = init_chat_model(
    "openai/gpt-oss-120b",
    model_provider="groq",
    temperature=0.1,
    timeout=60000,
    max_tokens=500,
)

model2 = init_chat_model(
    "openrouter:qwen/qwen3-30b-a3b-instruct-2507",
    temperature=0.1,
    timeout=60000,
    max_tokens=500,
)

if os.getenv("API_SELECT") == "groq" or not check_openrouter_key():
    model = model1
elif os.getenv("API_SELECT") == "openrouter" or check_openrouter_key():
    model = model2

tools = [create_json]

return create_agent(
    model=model,
    tools=tools,
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

| Item               | Valor atual                                 |
|--------------------|---------------------------------------------|
| Framework          | LangChain (`create_agent`)                  |
| Provider 1         | Groq (`init_chat_model`, `model_provider`) |
| Modelo 1           | `openai/gpt-oss-120b`                       |
| Provider 2         | OpenRouter (`init_chat_model`)              |
| Modelo 2           | `qwen/qwen3-30b-a3b-instruct-2507`          |
| `temperature`      | `0.1` (respostas determinísticas)           |
| `timeout`          | `60000` **milissegundos** (60 s)            |
| `max_tokens`       | `500`                                       |
| Ferramentas        | `create_json` (`tools=[create_json]`)       |
| Prompt de sistema  | `system_base.md` + `specific_role.md`       |

### Interface (CLI)

`src/nlq/main.py` monta o loop de conversa:

```python
agent.invoke({"messages": [{"role": "user", "content": user_input}]})["messages"][-1].content
```

Loop simples, sem histórico: cada pergunta é enviada isoladamente, com
`"sair"`, `"exit"` e `"quit"` como comandos de encerramento.

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

Definida em `src/nlq/tools/extract.py` e registrada em `tools=[create_json]`. É o
único mecanismo hoje para o agente acessar os dados.

```
LLM → create_json → csv.DictReader → JSON → LLM
```

```python
@tool
def create_json(name: str, ext: str) -> str
```

- `name` — nome do arquivo sem extensão, por exemplo `academia`.
- `ext` — extensão, por exemplo `csv`.
- Resolve `sheets/<ext>/<name>.<ext>` a partir da raiz do pacote.
- Devolve o **JSON da planilha inteira**, com `ensure_ascii=False`.

Requisitos ainda **não atendidos** pela implementação atual:

- Ausência de dado (`n/a`, célula vazia) não é sinalizada explicitamente — a tool
  devolve o dict cru.
- Falha de leitura não é explicada: erros como `FileNotFoundError` e
  `UnicodeDecodeError` sobem direto para o LLM, sem tratamento.
- Só lê **CSV**. Com `ext="xlsx"` a leitura levanta `UnicodeDecodeError`.
- Não é agnóstica de layout no acesso a disco: `ext` funciona ao mesmo tempo como
  extensão **e** como nome da pasta em `sheets/`.

## 5. Prompt de sistema

Montado por concatenação de dois arquivos Markdown em
`src/nlq/agent/prompts/`, lidos por `load_prompt()`:

- `system_base.md` — regras de funcionamento do agente.
- `specific_role.md` — **opcional**, define o escopo (papel, competência e base
  normativa). Vem com um exemplo de domínio e pode ser editado ou substituído
  livremente pelo usuário; o núcleo não depende do seu conteúdo.

Os nomes são string hardcoded na chamada em `create_nlq_agent()`: renomear um
arquivo exige atualizar essa referência, ou `load_prompt()` levanta
`FileNotFoundError` no startup.

## 6. Dívidas técnicas conhecidas

- **Parser XLSX inexistente** — `create_json` usa `csv.DictReader`; `ext="xlsx"`
  levanta `UnicodeDecodeError`.
- **BOM corrompe a primeira coluna** — os CSVs de `sheets/csv/` têm BOM UTF-8 e a
  tool abre com `encoding="utf-8"`, então o primeiro campo volta como
  `'\ufeffaluno'` em vez de `'aluno'`.
- **Path sem validação** — `name` e `ext` não são sanitizados, então `../../.env`
  escapa de `sheets/`.
- **`ext` acoplado ao layout** — a extensão também nomeia a pasta em `sheets/`.
- **Construção incondicional dos dois modelos** — exige `GROQ_API_KEY` mesmo
  usando OpenRouter.
- **Ausência de dado não sinalizada** pela tool (ver §4).
- **Sem histórico de conversa** entre turnos.
- Sem testes automatizados.
- `model` pode ficar sem atribuição quando `API_SELECT` é inesperado e a chave do
  OpenRouter é válida (ver [bug conhecido](#seleção-de-modelo)).
- `requests` usado em `agent.py` sem estar declarado em `pyproject.toml`.
- `check_openrouter_key()` faz uma chamada de rede a cada criação do agente
  (inclusive já coberta pela autodetecção, quando `API_SELECT` está vazio).

## 7. Evoluções possíveis

Detalhamento de ferramentas de esquema, RAG, NL2SQL, AST, validação e memória em
[`possible_implements.md`](possible_implements.md).
