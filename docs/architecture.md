# Arquitetura

## 1. Visão geral

O NLQ converte perguntas em linguagem natural em **consultas estruturadas** sobre
planilhas, priorizando fidelidade, confiabilidade e rastreabilidade. A arquitetura
é **agnóstica de planilha**: o núcleo não conhece fórmulas nem layouts específicos.

```
                         ┌──────────────────────────────────────┐
  Pergunta (PT-BR)       │              Núcleo NLQ              │
  ──────────────────────▶│                                      │
                         │  1. Entender a intenção              │
                         │  2. Localizar dados relevantes       │
                         │  3. Gerar consulta estruturada       │
                         │  4. Executar e validar               │
                         │  5. Responder + justificar           │
                         └───────────────┬──────────────────────┘
                                         │
             ┌───────────────────────────┼───────────────────────────┐
             ▼                           ▼                           ▼
      Camada de dados            Camada de consulta          Camada de agente
   (planilhas, esquema)          (NL2SQL / RAG / AST)        (LangChain + LLM)
```

## 2. Camadas

### 2.1 Camada de agente — **Atual**
Responsável pelo raciocínio e pela orquestração. Hoje é um único agente LangChain
criado em `create_nlq_agent()` (`src/nlq/agent/agent.py`), com o modelo acessado
via OpenRouter e prompt de sistema estático. Detalhes em [`agent.md`](agent.md).

### 2.2 Camada de dados (leitura de planilhas) — **A construir**
Abstrai a origem dos dados atrás de uma interface única, para que o núcleo não
dependa do formato do arquivo:

- **Descoberta de esquema**: nome das abas, colunas, tipos e hierarquia.
- **Leitura**: transformar a planilha em uma estrutura consultável (ex.: tabelas
  ou DataFrame), lidando com células mescladas, cabeçalhos em múltiplas linhas e
  valores `n/a` — comuns na planilha de teste.
- **Catálogo**: metadados que descrevem o que cada aba/coluna significa.

### 2.3 Camada de consulta — **A construir**
Traduz a intenção em operações sobre os dados. Estratégia evolutiva:

| Técnica   | Uso                                                     | Quando entra            |
|-----------|---------------------------------------------------------|-------------------------|
| `NL2SQL`  | Perguntas agregáveis/relacionais sobre tabelas          | Primeira etapa          |
| `RAG`     | Perguntas semânticas sobre texto livre das células      | Quando o léxico variar  |
| `AST`     | Análise estruturada/estatística sobre os dados          | Consultas complexas     |

As técnicas podem ser combinadas: recuperar candidatos via RAG e executar a
agregação via SQL/estruturada.

## 3. Fluxo de uma consulta

1. **Entrada** — pergunta do usuário (via CLI hoje, interface conversacional no futuro).
2. **Interpretação** — o agente identifica intenção, entidades e período/escopo.
3. **Planejamento** — decide qual ferramenta usar (dados, consulta, RAG).
4. **Geração** — produz uma consulta estruturada (SQL, Pandas, AST...).
5. **Execução** — roda a consulta contra a camada de dados.
6. **Validação** — confere se o resultado responde à pergunta (guarda-corpo de fidelidade).
7. **Resposta** — devolve o resultado **com a consulta/justificativa** (rastreabilidade).

## 4. Princípios de projeto

- **Fidelidade** — a resposta deve refletir exatamente os dados; nada de inferir
  valores ausentes.
- **Confiabilidade** — falhas de execução devem ser explícitas e recuperáveis, não
  silenciosas.
- **Rastreabilidade** — toda resposta é acompanhável até a consulta e a célula de
  origem.
- **Agnóstico de planilha** — o núcleo não pode assumir um layout específico.
- **Extensibilidade** — novas técnicas (RAG, AST, novos modelos) entram sem
  reescrever o núcleo.

## 5. Pontos de extensão previstos

- **Registro de ferramentas** (`tools=[]` em `agent.py`) → cada técnica de consulta
  vira uma ferramenta do agente.
- **Seleção de modelo** — o modelo é parametrizável em `create_nlq_agent()`; trocar
  de LLM via OpenRouter não exige mudar o núcleo.
  (CSV, múltiplas planilhas) não afeta o agente.

## 6. Dívidas técnicas conhecidas

- Agente sem ferramentas: responde "de cabeça", sem consultar dados.
- Sem memória/persistência de conversa (`session_id` não usado).
- Sem testes automatizados.
