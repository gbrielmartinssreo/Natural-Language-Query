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

O usuário pergunta, o agente (LangChain) leva a pergunta ao LLM, que decide o que consultar com base em regras que priorizam **busca semântica** para conteúdo. O agente conta com ferramentas para descobrir planilhas, consultar estrutura (schema), buscar de forma estruturada (Pandas), buscar por significado (RAG com embeddings) e, quando estritamente necessário, extrair registros completos. O checkpointer mantém o histórico da sessão em cada turno.

``` mermaid
sequenceDiagram
    autonumber
    actor U as Usuário
    participant A as Agente
    participant L as LLM
    participant T as Tools
    participant D as Dados

    U->>A: Pergunta
    A->>L: Pergunta + contexto + ferramentas
    L-->>A: Solicita execução de ferramenta
    A->>T: Executa ferramenta selecionada
    T->>D: Consulta arquivos
    D-->>T: Retorna dados
    T-->>A: Resultado
    A->>L: Resultado da ferramenta
    L-->>A: Resposta final
    A-->>U: Resposta
```

O agente é acessível por duas entradas — CLI (`src/nlq/main.py`) e API (`src/nlq/api.py`)— ambas compartilhando a mesma sessão em memória (`thread_id="default"`).

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

CLI funcional com agente conversando com um modelo. O agente tem
**memória da sessão** (`InMemorySaver` do LangGraph), então cada turno enxerga os
turnos anteriores da mesma execução, e a interface utiliza `rich` para melhorar a qualidade visual das respostas.

Há também uma **API FastAPI** (`src/nlq/api.py`) expondo o mesmo agente por HTTP
com **streaming NDJSON** (eventos `status`, `token`, `result`, `error`, `ping`), que serve a
**interface web**, que conta com: chat, loading, cancelamento de requisição, exibição de resposta e tratamento visual de
erro; falta a seleção/upload de planilha. 
As duas interfaces compartilham a mesma sessão (`thread_id="default"`), com bloqueio da limpeza de thread
durante uma consulta em andamento.

As **tools** disponíveis para leitura e descoberta de planilhas:

- `lista_arquivos` — descobre o que existe em `sheets/csv/` e `sheets/xlsx/`.
- `consultar_schema` — descreve estrutura (abas, regiões tabulares, cabeçalhos, colunas) **sem ler registros** (usa `xldetect`).
- `buscar_semantico` — busca semântica (RAG) com embeddings para localizar registros relevantes por significado (`top_k` entre 1 e 20).
- `create_json` — extrai registros completos quando estritamente necessário. Possui **guarda por tamanho** (bloqueia extração acima de ~20.000 caracteres) para evitar enviar planilhas grandes ao LLM.
- `consulta_dados` — busca estruturada com pandas para executar filtros, contagens, agregações e cálculos.

Os dois formatos são suportados: **CSV** com `csv.DictReader` e fallback de
codificação (`utf-8-sig` → `utf-8` → `cp1252` → `latin-1`), e **XLSX** com
`openpyxl` guiado por schema (`xldetect`), devolvendo registros organizados por abas.
O carregamento usa **cache em memória** (schema e registros) com invalidação por modificação do arquivo.

[`docs/scale_difficulties.md`](docs/scale_difficulties.md)).

## Próximos passos
[`docs/possible_implements.md`](docs/possible_implements.md)

## Requisitos

- [uv](https://docs.astral.sh/uv/)
- Python `>=3.14` (ver `.python-version`)
- Chaves de API do Openrouter/groq e Openai

## Configuração

Há um modelo com todas as variáveis em [`.env.example`](.env.example). Em
desenvolvimento, crie um `.env` na raiz do projeto.

Para fixar o provider, use `API_SELECT`:

```env
API_SELECT=openrouter   # ou groq
```

| `API_SELECT`  | Provider                                        |
|----------------|-------------------------------------------------|
| `groq`         | Groq — `openai/gpt-oss-120b`                    |
| `openrouter`   | OpenRouter — `deepseek/deepseek-v4-flash-0731`  |
| ausente        | Groq se a chave do OpenRouter for inválida; OpenRouter caso contrário |
| outro valor   | tratado como não-forçando Groq (segue lógica de detecção) |


A busca semântica usa **embeddings** (`text-embedding-3-small`) via API OpenAI, exigindo `OPENAI_API_KEY` (já presente em `.env.example`).


## Uso

### CLI

```bash
uv run nlq
```

Isso carrega o `.env`, cria o agente e abre o chat. Digite `sair` para encerrar.
O histórico vive em memória durante a execução: ao sair, a sessão é perdida.

A CLI (`rich`) é a interface de desenvolvimento.

### Interface web

```bash
uv run fastapi dev    # desenvolvimento (auto-reload) — http://127.0.0.1:8000
uv run fastapi run    # produção
```

A mesma API serve o frontend estático (`frontend/`): chat com balões de
mensagem, markdown (tabelas e código), loading animado durante o processamento,
indicador da planilha consultada, alternância de tema claro/escuro e status do
backend. A resposta usa streaming de tokens: o texto do modelo aparece
progressivamente e, ao final, é substituído pelo markdown renderizado.

### API

O mesmo agente é exposto pela API FastAPI (`src/nlq/api.py`), cujo entrypoint
está declarado no `pyproject.toml`:

```toml
[tool.fastapi]
entrypoint = "nlq.api:app"
```

A documentação interativa fica em `http://127.0.0.1:8000/docs`. O `.env` é
carregado no startup, então as mesmas chaves de API são necessárias.

| Rota                      | Método | O que faz                                                                                     |
|---------------------------|--------|-----------------------------------------------------------------------------------------------|
| `/`                       | GET    | serve o frontend (`frontend/index.html`, via `StaticFiles(html=True)`)                        |
| `/health`                 | GET    | health check (`{"status": "ok"}`)                                                             |
| `/api/chat`               | POST   | streaming NDJSON com eventos (`status`, `token`, `result`, `error`, `ping`). Corpo: `{"message": ..., "thread_id": ...}`. Eventos `token` trazem o texto parcial (`content`); o evento `result` traz `response` e `planilha` (`{"nome": ..., "ext": ...}` ou `null`). |
| `/api/limpar-conversa`    | DELETE | apaga a thread informada via `{"thread_id": ...}`. Retorna `409` se houver consulta em andamento para esse thread. |
| `/api/limpar-cache`       | DELETE | limpa os caches em RAM (índices semânticos, embeddings de consulta, DataFrames) e os `index-*.pkl` de `/tmp/nlq-cache/`, devolvendo contagens. Retorna `409` se houver consulta em andamento. Sem autenticação; há botão "Limpar caches" na interface web. |


A API compartilha o mesmo `checkpointer` com a CLI (memória em RAM). Por padrão a interface web usa `thread_id="default"`, mas o endpoint aceita `thread_id` por requisição. `DELETE /api/limpar-conversa` é bloqueado enquanto houver uma consulta ativa para o mesmo thread.

### Build automático (GitHub Actions)

O workflow [`.github/workflows/build.yml`](.github/workflows/build.yml) roda em
`push`/`pull_request` para `main` e `develop`, manualmente
(`workflow_dispatch`) e em tags `v*`. Em matriz `ubuntu-latest`/`windows-latest`,
publica os artefatos `NLQ-linux-x86_64.zip` e `NLQ-windows-x86_64.zip`. Em tags
`v*`, os dois ZIPs também são anexados a um **release**.

## Estrutura

```
src/nlq/
  main.py            # entry point (script `nlq`) — loop de chat com `rich`
  desktop.py         # entry point do executável — sobe a API local e abre o navegador
  api.py             # API FastAPI — streaming NDJSON (/api/chat), limpeza com bloqueio, health + frontend
  paths.py           # resolução de caminhos (desenvolvimento vs. empacotado)
  agent/
    agent.py         # create_nlq_agent(): deepagents + FilesystemBackend + seleção de modelo + regras → (agente, checkpointer)
    prompts/         # prompt de sistema montado por concatenação (system_base + specific_role + REGRAS_DE_CONSULTA)
    skills/          # skills do agente (SKILL.md por pasta) montadas em "/"
  data/              # schema (xldetect), loader com cache, embeddings, semantic_search, documents
  tools/
    extract.py       # create_json(): tool com guarda por tamanho (bloqueio > ~20k chars)
    listar_planilhas.py  # lista_arquivos(): tool de descoberta das planilhas
    schema_info.py       # consultar_schema(): estrutura sem registros
    retrieval.py         # buscar_semantico(): RAG com embeddings
    dev_master.py        # módulo auxiliar (não é tool de planilha)
frontend/
  index.html         # interface web — layout (sidebar, topbar, chat, composer)
  style.css          # tema claro/escuro, mensagens, tabelas, responsivo
  app.js             # consumo da API (stream NDJSON), render de markdown, loading, cancelamento, tema e status
sheets/
  csv/               # planilhas CSV
  xlsx/              # planilhas XLSX
nlq.spec             # spec do PyInstaller (distribuição em pasta)
.env.example         # modelo das variáveis de ambiente
.github/workflows/
  build.yml          # build Linux/Windows e release em tags `v*`
docs/
  architecture.md         # arquitetura atual e fluxo da consulta
  agent.md                # design do agente (deepagents, modelo, memória, tools, regras)
  development.md          # plano de branches, ambientes e deploy (milestone)
  possible_implements.md  # evoluções planejadas/realizadas (RAG, schema, Pandas etc)
  scale_difficulties.md   # escala de dificuldade das planilhas (dimensiona o parser)
```
