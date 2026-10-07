# Desenvolvimento, branches e ambientes

> **Status: planejado.** Este documento descreve o fluxo que será adotado na
> milestone [MVP com web / deploy / estabilidade](https://github.com/gbrielmartinssreo/Natural-Language-Query/milestone/2).
> Hoje o repositório está todo em `main`, sem deploy e rodando apenas localmente.

## 1. Fluxo de branches

O fluxo previsto ([issue #16](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/16)):

```text
feature/*  →  develop  →  main
             (teste)     (produção)
```

| Branch       | Papel                                                        |
|--------------|--------------------------------------------------------------|
| `feature/*`  | Desenvolvimento de uma mudança (issue, refactor, fix)        |
| `develop`    | Integração — deploy de teste automático a cada merge         |
| `main`       | Produção — deploy automático a cada merge                    |

Regras previstas:

- `main` é **protegida**: sem push direto, apenas pull request a partir de `develop`;
- `develop` aceita merges de `feature/*` via pull request;
- o fluxo é sempre `feature/* → develop → main`, sem pular etapas;
- correções urgentes entram por `fix/*` seguindo o mesmo caminho.

> Hoje só existe `main` e ela não está protegida — a criação de `develop` e a
> proteção de `main` são parte da issue #16.

## 2. Ambientes

Dois ambientes com deploy automático e URL fixa cada:

| Ambiente   | Branch     | Finalidade                              | Issue |
|------------|------------|------------------------------------------|-------|
| Desenvolvimento | `develop` | Testes antes de ir para produção      | [#17](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/17) |
| Produção        | `main`    | Uso do usuário final                 | [#18](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/18) |

### 2.1 Ambiente de desenvolvimento (issue #17)

- deploy ligado à branch `develop`;
- variáveis de ambiente próprias de dev (chaves de API de teste, quando aplicável);
- URL fixa de teste, estável entre deploys.

### 2.2 Ambiente de produção (issue #18)

- deploy ligado à branch `main`;
- variáveis de ambiente de produção (chaves reais, nunca as de dev);
- URL fixa de produção.

### 2.3 Variáveis de ambiente

O projeto já usa `.env` localmente (ver [`README.md`](../README.md#configuração)).
Nos ambientes hospedados, as mesmas variáveis passam a ser configuradas nas
**secrets/variables do provedor de deploy**, separadas por ambiente:

| Variável             | Desenvolvimento | Produção |
|----------------------|-----------------|----------|
| `OPENROUTER_API_KEY` | chave de teste  | chave real |
| `GROQ_API_KEY`       | chave de teste  | chave real |
| `API_SELECT`         | conforme necessidade do ambiente | conforme necessidade do ambiente |

O `.env` continua sendo usado apenas localmente e não deve ser commitado
(já está no `.gitignore`).

## 3. Deploy

Requisitos das issues #17 e #18:

- deploy **automático** por branch (push/merge dispara o deploy);
- **URL fixa** por ambiente, que não muda a cada deploy;
- configuração de variáveis de ambiente por ambiente.

A **API FastAPI** (`src/nlq/api.py`, entrypoint `[tool.fastapi]` no
`pyproject.toml`) é o ponto de entrada natural do deploy: `fastapi run` sobe o
servidor com a aplicação completa (agente + rotas + frontend estático).

> **Plataforma: decisão pendente.** Nenhuma plataforma foi escolhida ainda
> (opções comuns: Render, Railway, Fly.io, Vercel+backend, entre outras). A
> escolha não afeta este documento — os requisitos acima valem para qualquer
> plataforma.

## 4. Checklist de implementação

- [ ] Criar branch `develop` ([#16](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/16))
- [ ] Proteger `main` contra mudanças diretas ([#16](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/16))
- [ ] Documentar o fluxo `feature/* → develop → main` ([#16](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/16)) — este arquivo
- [ ] Escolher plataforma de deploy (decisão pendente)
- [ ] Deploy de teste ligado à `develop` com URL fixa ([#17](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/17))
- [ ] Variáveis de ambiente de dev configuradas ([#17](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/17))
- [ ] Deploy de produção ligado à `main` com URL fixa ([#18](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/18))
- [ ] Variáveis de ambiente de produção configuradas ([#18](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/18))

## 5. Relacionados

- Interface web (em andamento): [`possible_implements.md`](possible_implements.md) §7
  ([issue #19](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/19))
- Arquitetura atual: [`architecture.md`](architecture.md)
