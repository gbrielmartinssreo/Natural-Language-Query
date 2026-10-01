# Arquitetura

## 1. Visão geral

O NLQ responde **perguntas em linguagem natural** sobre dados de planilhas
(hoje CSV). O caminho é direto: o agente conversa com o LLM, o LLM decide o que
consultar, uma **ferramenta de planilha** devolve os dados em **JSON**, e o LLM
interpreta, calcula e redige a resposta final.

```mermaid
---
config:
  layout: dagre
---
flowchart LR
 subgraph LC["LangChain"]
        A["Agent"]
        L1["LLM"]
        T["Tool de Planilha"]
        J["JSON da Planilha"]
        R["Resposta final"]
  end
    U["Usuário"] --> Q["Pergunta"]
    X["CSV"] --> P["Parser"]
    P --> J
    Q --> A
    A --> L1
    L1 -- decide o que consultar --> T
    T --> J
    J --> L1
    L1 -- interpreta / calcula / redige --> R
    R --> U
```

O projeto é **agnóstico de planilha**: o núcleo não conhece fórmulas nem layouts
específicos. Detalhes do agente em [`agent.md`](agent.md).

## 2. Componentes

| Componente            | Onde                        | Papel                                                            | Estado       |
|-----------------------|-----------------------------|------------------------------------------------------------------|--------------|
| Interface (CLI)       | `src/nlq/main.py`           | Recebe a pergunta e imprime a resposta                            | **Atual**    |
| Agente (LangChain)    | `src/nlq/agent/agent.py`    | Orquestra o ciclo LLM ↔ ferramenta                               | **Atual**    |
| LLM (Groq/OpenRouter) | `src/nlq/agent/agent.py`    | Decide o que consultar, interpreta os dados e redige a resposta   | **Atual**    |
| Prompt de sistema     | `src/nlq/agent/prompts/`    | Dois arquivos Markdown concatenados em `system_prompt`           | **Atual**    |
| Tool de planilha      | `src/nlq/tools/extract.py`  | Tool `create_json` registrada no agente; expõe os dados da planilha | **Atual** |
| Parser (CSV)          | `src/nlq/tools/extract.py`  | Lê o CSV com `csv.DictReader` e converte para JSON                | **Atual**    |
| Parser (XLSX)         | —                           | Formato ainda não suportado                                        | **A implementar** |
| Resposta final        | `src/nlq/main.py`           | Texto devolvido ao usuário                                       | **Atual**    |

## 3. Fluxo de uma pergunta

1. **Entrada** — o usuário digita a pergunta na CLI.
2. **Agente → LLM** — o agente encaminha a pergunta ao modelo.
3. **Decisão** — o LLM decide o que precisa consultar na planilha.
4. **Consulta** — o LLM chama a **tool de planilha**; o **parser** lê o
   CSV e devolve o **JSON** da planilha.
5. **Volta ao LLM** — o JSON é devolvido ao modelo como contexto.
6. **Resposta** — o LLM interpreta, calcula e redige a resposta final.
7. **Saída** — a resposta é impressa para o usuário.

Não há etapa separada de validação, memória de conversa nem consulta em linguagem
estruturada: o LLM faz a interpretação e o cálculo sobre o JSON.

## 4. Princípios de projeto

- **Fidelidade** — a resposta deve refletir exatamente os dados; nada de inferir
  valores ausentes.
- **Confiabilidade** — falhas de execução devem ser explícitas e recuperáveis, não
  silenciosas.
- **Rastreabilidade** — a resposta é acompanhável até o dado de origem.
- **Agnóstico de planilha** — o núcleo não pode assumir um layout específico.
- **Extensibilidade** — novas ferramentas e novos modelos entram sem reescrever
  o núcleo.

O agnosticismo se mantém no **parser**, não na identidade: o arquivo de prompt
`specific_role.md` define o escopo do agente e é editável pelo usuário, sem que o
núcleo dependa do seu conteúdo.

## 5. Dívidas técnicas conhecidas

- **Parser XLSX inexistente** — `create_json` usa `csv.DictReader`, então
  `ext="xlsx"` levanta `UnicodeDecodeError`. O desafio final em `sheets/xlsx/` é
  inacessível.
- **BOM corrompe a primeira coluna** — os CSVs de `sheets/csv/` têm BOM UTF-8 e a
  tool abre com `encoding="utf-8"`, então o primeiro campo do `DictReader` volta
  como `'\ufeffaluno'` em vez de `'aluno'`.
- **Path sem validação** — `name` e `ext` não são sanitizados, então um `name`
  como `../../.env` escapa de `sheets/`.
- **As duas chaves de API são obrigatórias** — os dois modelos são construídos
  antes da escolha, logo falta de `GROQ_API_KEY` derruba a inicialização mesmo
  usando OpenRouter.
- Sem memória de conversa entre turnos.
- Sem testes automatizados.

## 6. Evoluções possíveis

Ideias fora do escopo atual (NL2SQL, RAG, AST, memória, validação, múltiplas
ferramentas) estão em [`possible_implements.md`](possible_implements.md).
