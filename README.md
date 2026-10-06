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
interpreta, calcula e redige a resposta final. Uma **tool de descoberta** permite
listar as planilhas disponíveis, e o checkpointer do agente carrega o histórico
da sessão em cada turno.

```
Usuário → Pergunta → Agente (memória da sessão) → LLM
   → lista_arquivos (descobre planilhas) | create_json → Parser (CSV | XLSX) → JSON
   → LLM → Resposta
```

Detalhes em [`docs/architecture.md`](docs/architecture.md).

## Prompts

O prompt de sistema é montado por concatenação de dois arquivos Markdown em
`src/nlq/agent/prompts/`:

- `system_base.md` — regras de funcionamento do agente: uso das ferramentas,
  continuidade da conversa e exibição completa da planilha quando pedida.
- `specific_role.md` — **opcional**. Define o escopo do agente (papel, competência e
  base normativa). Vem com um exemplo de domínio e pode ser editado ou substituído
  livremente pelo usuário; o núcleo do NLQ não depende do seu conteúdo.

A separação é o que mantém o projeto genérico: o mesmo agente atende contextos
diferentes trocando apenas esse arquivo.

## Estado atual

CLI funcional com agente LangChain conversando com um modelo. O agente tem
**memória da sessão** (`InMemorySaver` do LangGraph), então cada turno enxerga os
turnos anteriores da mesma execução, e a interface é `rich` (prompt, spinner de
raciocínio e Painel com Markdown na resposta).

São **duas tools de planilha**:

- `lista_arquivos` — descobre o que existe em `sheets/csv/` e `sheets/xlsx/`.
- `create_json` — lê o arquivo e devolve o **JSON** inteiro para o LLM
  interpretar.

Os dois formatos são suportados: **CSV** com `csv.DictReader` e fallback de
codificação (`utf-8-sig` → `utf-8` → `cp1252` → `latin-1`), e **XLSX** com
`openpyxl`, devolvendo **todas as abas** do arquivo (`{nome_da_aba: [linhas]}`).

`sheets/csv/` traz o escopo inicial (nível 1 da escala) e `sheets/xlsx/` traz
planilhas de nível 2 — com várias abas. Já a planilha
`MATRIZ ENCAMINHADA - FINAL.xlsx` (nível 4) é **legível**, mas sem tratamento de
células mescladas e cabeçalho multinível, então ainda não é confiável para
resposta (ver [`docs/scale_difficulties.md`](docs/scale_difficulties.md)).

## Próximos passos

Há duas milestones abertas no momento, com issues ainda não aplicadas — é o
plano imediato:

### [MVP com foco na análise da LLM](https://github.com/gbrielmartinssreo/Natural-Language-Query/milestone/1)

| Issue | Escopo |
|-------|--------|
| [#10](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/10) | Testes unitários para as tools existentes |
| [#12](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/12) | Persistência de contexto e técnica de compactação de tokens |
| [#15](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/15) | Skills de análise e listagem (formatação de listagens e passos de extração) |

### [MVP com web / deploy / estabilidade](https://github.com/gbrielmartinssreo/Natural-Language-Query/milestone/2)

| Issue | Escopo |
|-------|--------|
| [#16](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/16) | Fluxo de branches: criar `develop`, `main` como produção, proteger `main` |
| [#17](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/17) | Ambiente de desenvolvimento: deploy ligado à `develop`, env vars de dev, URL fixa de teste |
| [#18](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/18) | Ambiente de produção: deploy na `main`, env vars de produção, URL fixa |
| [#19](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/19) | Interface web: chat, seleção/upload de planilha, loading, resposta e tratamento visual de erro |

O fluxo de branches e os ambientes da segunda milestone estão detalhados em
[`docs/development.md`](docs/development.md); o escopo da interface web, em
[`docs/possible_implements.md`](docs/possible_implements.md) §7. A tecnologia da
interface web e a plataforma de deploy ainda são **decisões pendentes**.

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

Os dois modelos usam `temperature=0.1`, `timeout=60000` (ms) e
`max_tokens` de **7000** (Groq) ou **10000** (OpenRouter) — limite relevante
porque a tool de planilha envia a planilha inteira no contexto.


## Uso

```bash
uv run nlq
```

Isso carrega o `.env`, cria o agente e abre o chat. Digite `sair` para encerrar.
O histórico vive em memória durante a execução: ao sair, a sessão é perdida.

A CLI (`rich`) é a **interface atual** — a interface web faz parte da milestone
de web (ver [Próximos passos](#próximos-passos)).

## Estrutura

```
src/nlq/
  main.py            # entry point (script `nlq`) — loop de chat com `rich`
  agent/
    agent.py         # create_nlq_agent(): checkpointer + seleção de modelo + agente
    prompts/         # prompt de sistema montado por concatenação
  tools/
    extract.py       # create_json(): tool de leitura de planilha (CSV e XLSX)
    listar_planilhas.py  # lista_arquivos(): tool de descoberta das planilhas
    dev_master.py    # módulo auxiliar (não é tool de planilha)
sheets/
  csv/               # escopo inicial (nível 1)
  xlsx/              # planilhas multi-aba (níveis 2 e 4)
docs/
  architecture.md         # arquitetura atual e fluxo da consulta
  agent.md                # design do agente (modelo, memória, tools de planilha)
  development.md          # plano de branches, ambientes e deploy (milestone)
  possible_implements.md  # plano futuro (Pandas + RAG; AST/NL2SQL condicionais...)
  scale_difficulties.md   # escala de dificuldade das planilhas (dimensiona o parser)
```

## Evoluções possíveis

A próxima direção é evitar que planilhas grandes sejam enviadas inteiras ao LLM
em toda pergunta. O plano prioriza:

- **execução tabular local (Pandas)** para filtros, agregações e consultas exatas;
- **busca semântica/RAG** para localizar registros por significado;
- uso híbrido dos dois quando a pergunta combinar semântica e cálculo.

**AST** permanece como possibilidade futura caso a camada de consulta cresça a
ponto de precisar de uma representação intermediária própria. **NL2SQL** deixa
de ser prioridade para planilhas genéricas e fica reservado para fontes
relacionais reais ou dados claramente relacionais.

Persistência de sessão, validação de respostas e ferramentas de esquema também
continuam como evoluções possíveis.

[`docs/possible_implements.md`](docs/possible_implements.md)
