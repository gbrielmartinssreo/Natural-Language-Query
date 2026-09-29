# Agente

## 1. Papel

O agente é a camada de raciocínio e orquestração do NLQ. Ele recebe a pergunta em
linguagem natural, decide **como** responder (quais ferramentas usar) e devolve
uma resposta fiel, confiável e rastreável.

Hoje o agente **não tem ferramentas** — ele apenas conversa com o modelo. Toda a
capacidade de consultar planilhas virá de ferramentas registradas nele.

## 2. Implementação atual

Definido em `create_nlq_agent()` — `src/nlq/agent/agent.py`:

```python
model = init_chat_model(
    "openrouter:qwen/qwen3-30b-a3b-instruct-2507",
    temperature=0.1,
    timeout=60000,
    max_tokens=500,
)
return create_agent(model=model, tools=[], system_prompt="Você é um assistente útil e objetivo.")
```

| Item            | Valor atual                                   |
|-----------------|-----------------------------------------------|
| Framework       | LangChain (`create_agent`) + LangGraph        |
| Provider        | OpenRouter (`init_chat_model`)                |
| Modelo          | `qwen/qwen3-30b-a3b-instruct-2507`            |
| `temperature`   | `0.1` (respostas determinísticas)             |
| `timeout`       | `60000` **milissegundos** (60 s)              |
| `max_tokens`    | `500`                                          |
| Ferramentas     | nenhuma (`tools=[]`)                          |
| Prompt de sistema | genérico, provisório                        |

Entrada/saída via lista de mensagens:

```python
agent.invoke({"messages": [{"role": "user", "content": "..."}]})["messages"][-1].content
```

## 3. Configuração do modelo

O modelo é escolhido por uma string no formato `openrouter:<modelo>`. Trocar de
LLM não exige alterar o núcleo — basta mudar a string. Parâmetros relevantes:

- **`temperature`** — manter baixa (0–0.2): o foco é fidelidade, não criatividade.
- **`max_tokens`** — limita o tamanho da resposta.
- **`timeout`** — em **milissegundos** (ver armadilhas).

## 4. Ferramentas (a implementar)

O agente deve ganhar ferramentas em vez de responder "de cabeça". Proposta:

| Ferramenta            | Função                                                    |
|-----------------------|-----------------------------------------------------------|
| `listar_abas`         | Descreve abas/colunas disponíveis na planilha             |
| `ler_esquema`         | Retorna tipos, cabeçalhos e hierarquia de uma aba         |
| `consultar_dados`     | Executa consulta estruturada e retorna linhas/agregados   |
| `buscar_texto` (RAG)  | Recupera células relevantes por similaridade (futuro)     |

Regra: o agente **só** afirma um valor que veio de uma ferramenta. Sem isso, deve
dizer que não sabe.

## 5. Prompt de sistema

O prompt atual ("Você é um assistente útil e objetivo.") é provisório. A evolução
deve instruir explicitamente:

- Nunca inventar dados; usar ferramentas para obter valores.
- Devolver a resposta **e** a origem (aba/coluna/consulta) para rastreabilidade.
- Tratar `n/a` e células vazias como ausência de dado, não como zero.
- Pedir esclarecimento quando a pergunta for ambígua.

## 6. Roadmap do agente

1. Adicionar ferramentas de leitura/esquema da planilha.
2. Definir prompt de sistema com foco em fidelidade e rastreabilidade.
3. Introduzir validação da resposta contra a execução (guarda-corpo).
4. Avaliar memória de conversa (`session_id`) para consultas em múltiplos turnos.
5. Evoluir a seleção de técnicas (NL2SQL → RAG → AST) conforme a complexidade.
