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
Usuário → Pergunta → Agente → LLM → Tool de Planilha → Parser (CSV) → JSON → LLM → Resposta
```

Detalhes em [`docs/architecture.md`](docs/architecture.md).

## Prompts

O prompt de sistema é montado por concatenação de dois arquivos Markdown em
`src/nlq/agent/prompts/`:

- `system_base.md` — regras de funcionamento do agente.
- `specific_role.md` — **opcional**. Define o escopo do agente (papel, competência e
  base normativa). Vem com um exemplo de domínio e pode ser editado ou substituído
  livremente pelo usuário; o núcleo do NLQ não depende do seu conteúdo.

A separação é o que mantém o projeto genérico: o mesmo agente atende contextos
diferentes trocando apenas esse arquivo.

## Estado atual

CLI funcional com agente LangChain conversando com um modelo, já com a **tool de
planilha** (`create_json`) registrada. Ela lê um CSV de `sheets/` e devolve o JSON
inteiro para o LLM interpretar. O **parser é apenas CSV** — suporte a XLSX ainda
não existe (ver dívidas técnicas em [`docs/agent.md`](docs/agent.md)).

`sheets/csv/` traz o escopo inicial; a planilha em `sheets/xlsx/` é o **desafio
final** que o projeto deve ser capaz de enfrentar e hoje está fora de alcance.

## Requisitos

- [uv](https://docs.astral.sh/uv/)
- Python `>=3.14` (ver `.python-version`)
- Chaves de API do [OpenRouter](https://openrouter.ai/) **e** do
  [Groq](https://console.groq.com/keys)

> **Ambas são obrigatórias para iniciar.** `create_nlq_agent()` constrói os dois
> modelos antes de escolher entre eles, então a construção falha sem
> `GROQ_API_KEY` mesmo quando o provider escolhido é o OpenRouter.

## Configuração

Crie um `.env` na raiz do projeto:

```env
OPENROUTER_API_KEY=sua-chave-aqui
GROQ_API_KEY=sua-chave-aqui
```

A chave do OpenRouter é validada no startup: se a chamada falhar, o agente usa o
Groq. Para fixar o provider, use `API_SELECT`:

```env
API_SELECT=openrouter   # ou groq
```

| `API_SELECT`  | Provider                                        |
|----------------|-------------------------------------------------|
| `groq`         | Groq — `openai/gpt-oss-120b`                    |
| `openrouter`   | OpenRouter — `qwen/qwen3-30b-a3b-instruct-2507` |
| ausente        | Groq se a chave do OpenRouter for inválida; OpenRouter caso contrário |
| qualquer outro | `UnboundLocalError` — ver [bug conhecido](docs/agent.md#seleção-de-modelo) |


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
    prompts/         # prompt de sistema montado por concatenação
  tools/
    extract.py       # create_json(): tool de leitura de planilha (CSV)
sheets/
  csv/               # escopo inicial (nível 1)
  xlsx/              # desafio final (nível 4)
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
