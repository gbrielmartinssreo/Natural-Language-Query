# Natural Language Query (NLQ)

O **NLQ** é um projeto voltado à consulta e interpretação de dados armazenados em
planilhas por meio de **linguagem natural**.

A proposta é oferecer uma interface conversacional capaz de transformar perguntas
do usuário em consultas estruturadas sobre os dados, priorizando **fidelidade,
confiabilidade e rastreabilidade das respostas**.

O objetivo é ser **genérico**: operar sobre diferentes planilhas e contextos sem
exigir que o usuário conheça fórmulas, estruturas de tabelas ou linguagens de
consulta.

## Estado atual

Esqueleto funcional: um agente LangChain que conversa com um modelo via
OpenRouter. Ainda **não há ferramentas de leitura de planilha** ligadas ao agente
(`tools=[]`) — o pipeline de consulta aos dados está em desenvolvimento.

A planilha em `sheets/` é o **desafio final** que o projeto deve ser capaz de
enfrentar, não o escopo inicial.

## Requisitos

- [uv](https://docs.astral.sh/uv/)
- Python `>=3.14` (ver `.python-version`)
- Uma chave de API do [OpenRouter](https://openrouter.ai/)

## Configuração

Crie um `.env` na raiz do projeto:

```env
OPENROUTER_API_KEY=sua-chave-aqui
```

## Uso

```bash
uv run nlq
```

Isso carrega o `.env`, cria o agente e envia uma pergunta de exemplo ao modelo.

## Estrutura

```
src/nlq/
  main.py            # entry point (script `nlq`)
  agent/
    agent.py         # create_nlq_agent(): modelo + agente LangChain
sheets/              # planilhas de teste (desafio final)
docs/
  architecture.md    # visão de arquitetura e roadmap de extensão
  agent.md           # design do agente (modelo, prompt, ferramentas, guardrails)
```

## Roadmap

Começa com uma abordagem baseada em agentes (**LangChain + OpenRouter**) e evolui
conforme a complexidade das consultas:

- **NL2SQL** — traduzir a pergunta em consultas estruturadas.
- **RAG** — recuperação semântica sobre o conteúdo das planilhas.
- **AST** — manipulação estruturada/analítica dos dados.

Detalhes em [`docs/architecture.md`](docs/architecture.md).
