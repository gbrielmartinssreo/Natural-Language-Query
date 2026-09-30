# Natural Language Query (NLQ)

![Status do Projeto](https://img.shields.io/badge/Status-Desenvolvimento-yellow)


O **NLQ** é um projeto voltado à consulta e interpretação de dados armazenados em
planilhas por meio de **linguagem natural**.

A proposta é oferecer uma interface conversacional que responde perguntas do
usuário a partir dos dados da planilha, priorizando **fidelidade, confiabilidade
e rastreabilidade das respostas**.

O objetivo é ser **genérico**: operar sobre diferentes planilhas e contextos sem
exigir que o usuário conheça fórmulas, estruturas de tabelas ou linguagens de
consulta.

## Arquitetura

O usuário pergunta, o agente (LangChain) leva a pergunta ao LLM, o LLM decide o
que consultar, uma **tool de planilha** devolve o **JSON** dos dados, e o LLM
interpreta, calcula e redige a resposta final.

```
Usuário → Pergunta → Agente → LLM → Tool de Planilha → Parser (XLSX/CSV) → JSON → LLM → Resposta
```

Detalhes em [`docs/architecture.md`](docs/architecture.md).

## Estado atual

CLI funcional com agente LangChain conversando com um modelo. A **tool de
planilha** e o **parser** ainda não existem (`tools=[]`) — são o próximo passo.

A planilha em `sheets/` é o **desafio final** que o projeto deve ser capaz de
enfrentar, não o escopo inicial.

## Requisitos

- [uv](https://docs.astral.sh/uv/)
- Python `>=3.14` (ver `.python-version`)
- Uma chave de API do [OpenRouter](https://openrouter.ai/) **ou** do
  [Groq](https://console.groq.com/keys)

## Configuração

Crie um `.env` na raiz do projeto:

```env
OPENROUTER_API_KEY=sua-chave-aqui
```

A chave do OpenRouter é validada no startup: se a chamada falhar, o agente cai
automaticamente para o Groq. Para fixar o provider, use `API_SELECT`:

```env
API_SELECT=openrouter   # ou groq
```

| `API_SELECT`  | Provider                                        |
|----------------|-------------------------------------------------|
| `groq`         | Groq — `openai/gpt-oss-120b`                    |
| `openrouter`   | OpenRouter — `qwen/qwen3-30b-a3b-instruct-2507` |
| ausente/outro  | Groq se a chave do OpenRouter for inválida; OpenRouter caso contrário |


## Uso

```bash
uv run nlq
```

Isso carrega o `.env`, cria o agente e abre o chat. Digite `sair` para encerrar.

## Estrutura

```
src/nlq/
  main.py            # entry point (script `nlq`)
  agent/
    agent.py         # create_nlq_agent(): seleção de modelo + agente LangChain
sheets/              # planilhas de teste (desafio final)
docs/
  architecture.md         # arquitetura atual e fluxo da consulta
  agent.md                # design do agente (modelo, prompt, tool de planilha)
  possible_implements.md  # evoluções futuras (NL2SQL, RAG, AST, memória...)
  scale_difficulties.md   # escala de dificuldade das planilhas (dimensiona o parser)
```

## Evoluções possíveis

Ideias fora do escopo atual — `NL2SQL`, `RAG`, `AST`, memória de conversa,
validação da resposta e ferramentas de esquema:

[`docs/possible_implements.md`](docs/possible_implements.md)
