---
name: consultar-schema
description: Use quando a pergunta sobre uma planilha puder ser respondida só com a estrutura (abas, regiões tabulares, cabeçalhos, nomes de colunas), sem ler os registros. Exemplos - quais abas existem, quais colunas tem uma aba, como a planilha está organizada, em quais abas existe uma coluna.
---

# Consultar o schema de uma planilha

A ferramenta consultar_schema identifica a estrutura da planilha sem retornar todos os registros.

## Quando usar

Use `consultar_schema` para perguntas como:

- Quais abas existem?
- Quais colunas existem em determinada aba?
- Como a planilha está organizada?
- Em quais abas existe determinada coluna?

## Quando NÃO usar
- Para encontrar iniciativas relacionadas a um assunto: use buscar_semantico.
- Para contar, somar ou filtrar todos os registros: use uma ferramenta de consulta estruturada, quando disponível.
- Para analisar todos os dados em conjunto: considere create_json, se a extração completa for realmente necessária.
Se a pergunta exigir estrutura e conteúdo, consulte o schema somente quando isso ajudar a localizar ou interpretar os dados.

## Como chamar

`consultar_schema(name, ext, aba=None)`

- `name`: nome do arquivo sem extensão (`matriz`).
- `ext`: `xlsx` ou `csv`.
- `aba` (opcional): nome de uma aba. Informe quando a pergunta for sobre
  uma aba específica; a resposta fica menor. Maiúsculas e minúsculas são
  ignoradas. Se a aba não existir, o erro lista as abas disponíveis.

Para perguntas sobre a planilha inteira ("em quais abas existe a coluna X?",
"como está organizada?"), chame **sem** `aba`: uma só chamada traz todas as
abas.

## Como ler a resposta

Para cada aba, a resposta lista as regiões tabulares detectadas:

```
Aba 'Eixo 1': 2 regiões
  Região 1: A1:D20 (linhas 1 a 20, colunas 1 a 4)
    cabeçalho na linha 1; dados a partir da linha 2
    colunas (4): ["Nome", "Responsável", "coluna_3", "Status"]
```

- A faixa (`A1:D20`) e os números de linha/coluna delimitam a região.
- Uma aba pode ter várias regiões (tabelas empilhadas ou lado a lado);
  cada uma tem suas próprias colunas.
- `sem cabeçalho detectado` significa que a primeira linha da região também
  é dado; as colunas têm nomes gerados.
- `coluna_N` é um nome **gerado** (cabeçalho ausente ou vazio), com N sendo
  o número da coluna na aba. Não é um título real da planilha.
- `nenhuma região tabular detectada` indica aba vazia ou sem estrutura de
  tabela.
- Ao responder "em quais abas existe a coluna X", compare os nomes de
  coluna de todas as abas e regiões, ignorando diferenças entre maiúsculas
  e minúsculas, e cite a aba e a região onde ela aparece.

## CSV

CSV não tem abas nem regiões, então não existe schema estrutural. A
ferramenta informa isso explicitamente e não lista colunas.

## Cuidados

- Não invente colunas, abas ou valores que não apareçam na resposta.
- A resposta não contém registros. Nunca responda sobre conteúdo de células
  com base nela.
- Se a pergunta exigir valores, selecione buscar_semantico para assuntos específicos ou consulta estruturada para resultados exatos.
- Não use o schema sozinho para responder perguntas sobre valores das células.

## Escolha e resposta

Perguntas sobre assuntos, medidas, iniciativas e metas específicas devem começar por buscar_semantico, sem consulta estrutural obrigatória.
Para “sobre o que é a planilha?”, não confunda descrição da estrutura com compreensão do conteúdo. O schema sozinho não sustenta afirmações sobre valores.
Responda somente com os detalhes estruturais pedidos. Não liste todos os intervalos e cabeçalhos se o usuário só pediu uma visão breve.
