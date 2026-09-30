# Agente

## 1. Papel

O agente é a camada de raciocínio e orquestração do NLQ. Ele recebe a pergunta em
linguagem natural, **consulta a planilha através de uma ferramenta** e devolve uma
resposta fiel e rastreável.

O LLM é quem decide o que consultar, interpreta o JSON retornado e redige a
resposta — não há etapas rigidamente separadas no código.

## 2. Implementação atual

Definido em `create_nlq_agent()` — `src/nlq/agent/agent.py`:

```python
model = init_chat_model(
    "openrouter:qwen/qwen3-30b-a3b-instruct-2507",
    temperature=0.1,
    timeout=60000,
    max_tokens=500,
)

return create_agent(
    model=model,
    tools=[],
    system_prompt="Você é um assistente útil e objetivo.",
)
```

| Item               | Valor atual                        |
|--------------------|------------------------------------|
| Framework          | LangChain (`create_agent`)         |
| Provider           | OpenRouter (`init_chat_model`)     |
| Modelo             | `qwen/qwen3-30b-a3b-instruct-2507` |
| `temperature`      | `0.1` (respostas determinísticas)  |
| `timeout`          | `60000` **milissegundos** (60 s)   |
| `max_tokens`       | `500`                              |
| Ferramentas        | nenhuma (`tools=[]`) — **a implementar** |
| Prompt de sistema  | genérico, provisório               |

### Interface (CLI)

`src/nlq/main.py` monta o loop de conversa:

```python
agent.invoke({"messages": [{"role": "user", "content": user_input}]})["messages"][-1].content
```

Loop simples, sem histórico: cada pergunta é enviada isoladamente, com
`"sair"`, `"exit"` e `"quit"` como comandos de encerramento.

## 3. Configuração do modelo

O modelo é escolhido por uma string no formato `openrouter:<modelo>`. Trocar de
LLM não exige alterar o núcleo — basta mudar a string. Parâmetros relevantes:

- **`temperature`** — manter baixa (0–0.2): o foco é fidelidade, não criatividade.
- **`max_tokens`** — limita o tamanho da resposta.
- **`timeout`** — em **milissegundos** (ver armadilhas).

## 4. Tool de planilha (a implementar)

É o único mecanismo previsto hoje para o agente acessar os dados: uma tool que
recebe a solicitação do LLM, chama o **parser** e devolve o **JSON** da planilha.

```
LLM → tool de planilha → parser (XLSX/CSV) → JSON → LLM
```

Requisitos da tool:

- Receber a pergunta/consulta do LLM e devolver **JSON** legível pelo modelo.
- Ser agnóstica de layout — o núcleo não assume uma planilha específica.
- Sinalizar ausência de dado (`n/a`, célula vazia) explicitamente, para que o LLM
  não trate ausência como zero.
- Falhar de forma explícita quando o arquivo não puder ser lido, em vez de
  devolver resultado parcial silencioso.

## 5. Prompt de sistema

O prompt atual ("Você é um assistente útil e objetivo.") é provisório. Deve
passar a instruir explicitamente:

- Nunca inventar dados; usar a tool para obter valores.
- Tratar `n/a` e células vazias como ausência de dado, não como zero.
- Devolver a resposta **e** a origem (arquivo/aba/coluna) para rastreabilidade.
- Pedir esclarecimento quando a pergunta for ambígua.

## 6. Dívidas técnicas conhecidas

- Tool de planilha e parser ainda não existem — `tools=[]`.
- Prompt de sistema sem regras de fidelidade.
- Sem histórico de conversa entre turnos.
- Sem testes automatizados.

## 7. Evoluções possíveis

Detalhamento de ferramentas de esquema, RAG, NL2SQL, AST, validação e memória em
[`possible_implements.md`](possible_implements.md).
