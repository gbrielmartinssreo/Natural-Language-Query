# Implementações Possíveis

Este documento reúne ideias **fora do escopo atual** do NLQ e organiza a direção
de evolução do projeto.

O estado atual e a arquitetura em vigor estão em
[`architecture.md`](architecture.md) e [`agent.md`](agent.md).

---

## 1. Próxima direção: reduzir o contexto enviado ao LLM

A tool atual (`create_json`) devolve a planilha inteira em JSON. Isso funciona
bem para arquivos pequenos e foi suficiente para validar o agente, mas não escala:
o principal gargalo passa a ser o **volume de dados enviado ao modelo em cada
pergunta**, não apenas o tempo de leitura do arquivo.

Cachear o XLSX em memória pode evitar releitura e parsing, mas **não resolve o
problema principal** se o JSON completo continuar sendo enviado ao LLM.

A próxima evolução deve separar:

- **leitura/preparação local** — abrir e normalizar a planilha;
- **seleção local** — localizar somente os registros necessários;
- **LLM** — interpretar a pergunta e redigir a resposta a partir de um contexto
  reduzido.

Ferramentas candidatas:

| Ferramenta | Função |
|---|---|
| `listar_abas` | Descreve abas e colunas disponíveis |
| `ler_esquema` | Retorna cabeçalhos, tipos e características da aba |
| `consultar_dados` | Executa filtros, agregações e ordenações localmente |
| `buscar_semantico` | Recupera registros por similaridade de significado |

O objetivo é que uma pergunta sobre 10 registros relevantes não obrigue o modelo
a reler milhares de linhas.

---

## 2. Estratégia de consulta: tabular + semântica

A direção principal é uma arquitetura híbrida, porque planilhas genéricas podem
ter tanto dados estruturados quanto campos textuais fortemente semânticos.

```text
Pergunta
   ↓
decisão de estratégia
   ↓
┌────────────────────┬─────────────────────┐
│ consulta exata     │ consulta semântica  │
│ Pandas / executor  │ embeddings / vetor  │
└────────────────────┴─────────────────────┘
           ↓
      poucos dados
           ↓
          LLM
```

### 2.1 Pandas / execução tabular — prioridade

É a primeira evolução para perguntas como:

- contagens;
- filtros;
- ordenações;
- soma, média, mínimo e máximo;
- agrupamentos;
- cruzamentos simples entre dados já identificados.

O objetivo não é deixar o LLM gerar código Pandas arbitrário, mas usar uma tool
controlada que receba uma operação estruturada e execute localmente.

### 2.2 Busca semântica / RAG — prioridade

É indicada para planilhas com campos de texto em que a pergunta e a célula podem
usar vocabulários diferentes, por exemplo:

- "reintegração social" ↔ "apoio ao egresso";
- "fortalecimento institucional" ↔ ações descritas sem esse termo literal;
- localização de medidas, observações ou descrições relacionadas por significado.

A unidade de indexação deve preservar o registro original e seus metadados
(aba, linha, colunas relevantes). O vetor serve para **encontrar candidatos**;
valores exatos, contagens e agregações continuam sendo executados sobre os dados
estruturados.

### 2.3 Consultas híbridas

Perguntas podem exigir os dois mecanismos:

```text
"Entre as medidas relacionadas à reintegração,
quantas têm meta no Ano 2?"
```

Fluxo esperado:

1. busca semântica encontra os registros relacionados à reintegração;
2. executor tabular filtra `Meta Ano 2`;
3. executor calcula a contagem;
4. LLM recebe apenas o resultado e as evidências necessárias.

### 2.4 AST — possível, mas não prioritária

Uma representação intermediária estruturada (AST/plano de consulta) pode ser útil
no futuro se o roteamento e as operações crescerem a ponto de exigir uma linguagem
interna comum para `filter`, `aggregate`, `sort`, `semantic_search` etc.

Não é prioridade agora. Implementá-la antes dessa complexidade aparecer criaria
uma engine de consulta antes de existir necessidade concreta.

### 2.5 NL2SQL — caso especializado

NL2SQL deixa de ser uma evolução principal do NLQ de planilhas.

Ele é útil quando a fonte já é **relacional de verdade**, com schema estável,
chaves e tabelas relacionadas, ou quando uma planilha excepcionalmente bem
estruturada puder ser convertida para um banco temporário com relações claras.

Para planilhas genéricas, semi-estruturadas ou sem relações formais, Pandas e
busca semântica oferecem melhor relação entre simplicidade e utilidade.

| Técnica | Prioridade | Papel |
|---|---:|---|
| Pandas / executor tabular | Alta | consultas exatas e agregações |
| Busca semântica / RAG | Alta | recuperação por significado |
| AST / plano estruturado | Posterior | organizar consultas complexas se necessário |
| NL2SQL | Condicional | bancos relacionais ou dados claramente relacionais |

---

## 3. Edição assistida por IA

O sistema pode permitir que o usuário modifique planilhas usando linguagem
natural.

Exemplos:

- alterar valores;
- preencher campos;
- adicionar linhas;
- remover registros;
- atualizar colunas;
- aplicar regras em várias linhas;
- modificar fórmulas;
- realizar ajustes de formatação.

A LLM não deve editar diretamente o arquivo. Ela deve interpretar o pedido e gerar
uma operação estruturada, que é validada e executada localmente.

Exemplo conceitual:

```json
{
  "action": "update_cells",
  "sheet": "Alunos",
  "where": {
    "RA": 2026001
  },
  "changes": {
    "Ativo": false
  }
}
```

Fluxo esperado:

```text
Usuário
   ↓
LLM interpreta a alteração
   ↓
operação estruturada
   ↓
validação
   ↓
executor local
   ↓
openpyxl / Pandas
   ↓
novo arquivo
```

Para arquivos XLSX, `openpyxl` tende a ser a principal ferramenta de edição,
pois permite trabalhar diretamente com células, fórmulas, estilos e estrutura
do workbook.

Pandas pode continuar sendo usado para transformações tabulares em massa.

### Segurança e rastreabilidade

Por padrão:

- não sobrescrever o arquivo original;
- salvar uma nova versão;
- registrar as alterações realizadas;
- permitir visualizar um diff antes da aplicação;
- validar aba, linha, coluna e tipos antes de editar.

Isso permite transformar o NLQ de um sistema somente de consulta em um sistema de
**consulta e manipulação de planilhas por linguagem natural**.

---

## 4. Dashboards automáticos

A camada tabular também pode alimentar dashboards.

O papel do Pandas seria preparar os dados:

```text
planilha
   ↓
parser
   ↓
Pandas
   ↓
filtros / agregações / métricas
   ↓
dashboard
```

Possíveis elementos:

- indicadores e cards;
- totais;
- médias;
- máximos e mínimos;
- rankings;
- distribuições;
- séries temporais;
- gráficos por categoria;
- filtros por coluna, aba, período ou grupo.

A LLM pode participar principalmente da **seleção dos indicadores relevantes**.

Exemplo:

```text
Usuário:
"crie uma visão geral dessa planilha"

↓
LLM identifica métricas úteis
↓
executor tabular calcula
↓
frontend renderiza os gráficos
```

Os valores do dashboard devem ser calculados localmente, e não pelo modelo.

Assim, o mesmo motor tabular usado para responder perguntas pode servir também
para geração de dashboards.

### 4.1 Dashboard assistido por IA

Uma evolução adicional é permitir perguntas como:

```text
"quais indicadores são mais importantes nessa planilha?"
```

ou:

```text
"monte um dashboard de desempenho"
```

A LLM pode produzir uma descrição estruturada:

```json
{
  "metrics": [
    {
      "type": "sum",
      "column": "Valor",
      "title": "Valor total"
    },
    {
      "type": "count",
      "column": "Cliente",
      "title": "Clientes"
    }
  ],
  "charts": [
    {
      "type": "bar",
      "group_by": "Categoria",
      "value": "Valor"
    }
  ]
}
```

O backend executa as operações com Pandas e o frontend apenas renderiza.

Essa separação mantém o modelo como planejador e evita depender da LLM para
cálculos numéricos.

---

## 5. Validação da resposta

Conferir se o resultado devolvido responde à pergunta antes de responder ao
usuário.

Essa camada pode detectar:

- valores inventados;
- consultas que retornam vazio sem motivo aparente;
- filtros incompatíveis com a estrutura;
- divergências entre resultado calculado e resposta final;
- uso de registros sem origem rastreável.

A validação ganha importância quando o NLQ passa a combinar busca semântica,
operações tabulares e edição de arquivos.

---

## 6. Persistência de sessão

A memória **por execução** já existe: `InMemorySaver` do LangGraph, com um
`thread_id` fixo em `"default"` — compartilhado pela CLI (`main.py`) e pela API
(`api.py`), que enxergam a mesma sessão.

Follow-ups funcionam porque o estado volta no `invoke`.

Possíveis evoluções:

- checkpointer persistente (SQLite ou Postgres);
- múltiplas threads;
- política de tamanho do histórico;
- resumo ou trimming de conversas longas;
- separação entre memória conversacional e conhecimento persistente.

Persistência não é prioridade enquanto existir uma única sessão por execução,
mas ganha relevância quando o frontend web (issue
[#19](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/19))
passar a ser servido pela API: aí o histórico precisa sobreviver ao processo e
separar usuários.

---

## 7. Interface web e deploy

> **Em andamento na milestone aberta**
> [MVP com web / deploy / estabilidade](https://github.com/gbrielmartinssreo/Natural-Language-Query/milestone/2).
> O **backend já existe**: a API FastAPI (`src/nlq/api.py`) expõe o agente por
> HTTP. Falta o frontend e o restante do escopo da issue #19; a interface de
> desenvolvimento continua sendo a CLI.

A CLI atual permanece como interface de desenvolvimento.

Como a lógica principal está separada da `main.py`, a API e o futuro frontend
reutilizam o mesmo núcleo sem alterar agente, tools ou parser.

### 7.1 Escopo do MVP web (issue #19)

Requisitos mínimos da
[issue #19](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/19):

- chat;
- seleção/upload de planilha;
- loading durante o processamento;
- exibição da resposta;
- tratamento visual de erro.

**Backend: FastAPI definido** (`src/nlq/api.py`, com `POST /api/chat`,
`DELETE /api/limpar-conversa` e `GET /health`; entrypoint
`nlq.api:app` em `[tool.fastapi]` no `pyproject.toml`).

**Camada de UI: decisão pendente.** As duas rotas mapeadas são:

| Opção | Perfil |
|---|---|
| Streamlit | prototipagem rápida, pouco código |
| Frontend (React/Next) sobre a API FastAPI | mais controle, caminho já descrito abaixo |

### 7.2 Fora do escopo do MVP (futuro)

- preview de abas e tabelas interativas;
- dashboard e gráficos;
- filtros;
- histórico da conversa além da sessão;
- edição assistida, preview das alterações e download do arquivo modificado;
- visualização das evidências usadas na resposta.

### 7.3 Deploy

Os ambientes, o fluxo de branches (`feature/* → develop → main`) e os requisitos
de deploy (URL fixa por ambiente, variáveis de ambiente separadas) estão em
[`development.md`](development.md) — issues
[#16](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/16),
[#17](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/17) e
[#18](https://github.com/gbrielmartinssreo/Natural-Language-Query/issues/18).
A plataforma de deploy também é decisão pendente.

### 7.4 Arquitetura conceitual

Estrutura conceitual:

```text
core
├── parser
├── consulta tabular
├── busca semântica
├── edição
├── geração de métricas
└── agente

interfaces
├── CLI    (main.py — atual)
├── API    (api.py — atual)
└── Web    (frontend — pendente)
```

Arquitetura alvo, com a camada FastAPI **já implementada** e o frontend pendente:

```text
Frontend
React / Next.js        (pendente)
      ↓
FastAPI                (src/nlq/api.py — atual)
      ↓
NLQ Core
      ↓
Pandas / openpyxl / busca semântica
```

Uma alternativa mais simples para a UI seria Streamlit.

---

## 8. Pontos de extensão já previstos no código

- **Registro de ferramentas** (`tools=[create_json, lista_arquivos]` em `agent.py`)
  — cada técnica de consulta pode virar uma tool do agente.
- **Seleção de modelo** — o modelo é parametrizável em `create_nlq_agent()`.
- **Troca de fonte de dados** — CSV e XLSX já são lidos; outros formatos podem
  ser adicionados posteriormente.
- **Escopo do agente** — `prompts/specific_role.md` permite trocar o papel do
  agente sem alterar o núcleo.
- **Interfaces desacopladas** — a CLI está concentrada em `main.py` e a API em
  `api.py`; o frontend web pode se conectar à API sem tocar no núcleo.

---

## 9. Escala de dificuldade das planilhas

A referência para dimensionar o parser está em
[`scale_difficulties.md`](scale_difficulties.md).

Hoje:

- nível 1 (CSV limpo): suportado;
- nível 2 (XLSX simples): suportado;
- nível 3 (XLSX semi-estruturado): lido de forma bruta;
- nível 4 (planilha corporativa complexa): acessível, mas ainda não confiável.

Melhorar o parser para mesclagens, cabeçalhos multinível e múltiplos blocos por aba
continua sendo importante, especialmente para busca semântica e edição.

---

## 10. Visão de longo prazo

Com essas extensões, o NLQ deixa de ser apenas um chat que lê planilhas e passa a
funcionar como uma camada genérica de interação com dados tabulares.

```text
                    NLQ
                     │
        ┌────────────┼─────────────┐
        │            │             │
     Consulta      Edição       Dashboard
        │            │             │
        └───────┬────┴─────┬───────┘
                │          │
              Pandas    openpyxl
                │          │
                └────┬─────┘
                     │
              dados estruturados
                     │
         ┌───────────┴───────────┐
         │                       │
consulta exata             busca semântica
         │                       │
         └───────────┬───────────┘
                     │
                    LLM
```

A prioridade é manter a LLM como camada de **interpretação, planejamento e
apresentação**, enquanto operações exatas permanecem em ferramentas
determinísticas.
