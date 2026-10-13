---
name: read-file
description: Use para consultar, ler, resumir ou analisar arquivos. Localize o arquivo com lista_arquivos. Para perguntas sobre conteúdo, incluindo temas gerais, resumos de abas e eixos, use buscar_semantico primeiro. Use consultar_schema para estrutura. Reserve create_json para extração completa explicitamente solicitada ou necessária à tarefa. Peça confirmação se houver ambiguidade.
---

# Leitura e análise de arquivos

## Localização

1. Use lista_arquivos para localizar o arquivo.
2. Se não encontrar, informe isso sem inventar arquivos ou caminhos.
3. Se houver múltiplas correspondências plausíveis, peça confirmação.
4. Com o arquivo identificado, escolha a consulta pelas regras abaixo.

## Regra principal: conteúdo começa pelo RAG

Para perguntas sobre o conteúdo, use buscar_semantico como primeira
consulta, inclusive quando o usuário pedir uma explicação geral,
um resumo ou uma visão geral de uma aba, eixo ou tema.

Exemplos:
- "O eixo 1 aborda o quê no geral?"
- "Sobre o que é essa planilha?"
- "Resuma as propostas do eixo 2."
- "Quais iniciativas tratam de educação?"
- "O que o arquivo diz sobre saúde?"

Esses pedidos NÃO autorizam extração completa por padrão.

Não chame consultar_schema antes do RAG por rotina.
Não chame create_json apenas para confirmar informações já
sustentadas pelos resultados recuperados.

## Perguntas sobre estrutura

Use consultar_schema para identificar:
- Abas disponíveis.
- Colunas e cabeçalhos.
- Regiões tabulares.
- Organização estrutural da planilha.

Não use o schema sozinho para afirmar o conteúdo dos registros.

## Quando usar create_json

Use create_json somente quando:
- O usuário solicitar explicitamente todos os registros ou conteúdo completo.
- A tarefa exigir cobertura completa e não houver uma ferramenta
  estruturada adequada.
- O RAG já tiver sido consultado e a informação necessária continuar
  indisponível, com uma necessidade concreta de extração ampla.

Uma pergunta ser geral ou usar "ler", "analisar" ou "resumir"
não é motivo suficiente para extrair toda a planilha.

## Consultas exatas ou completas

Para contagens, somas, médias, filtros exatos ou comparações
que precisem de todos os registros, priorize uma ferramenta
de consulta estruturada.

Se não houver essa ferramenta, use extração completa quando
necessário. Não faça uma busca semântica apenas para cumprir
uma etapa que não resolve a tarefa.

Nunca calcule totais completos usando somente os resultados do RAG.

## Uso dos resultados do RAG

- Comece com top_k=5.
- Confira se os registros respondem à pergunta.
- Para pedidos sobre uma aba ou eixo, confira a origem de cada resultado.
- Mencionar uma aba na query não equivale a filtrar por essa aba.
- Descarte resultados de outro escopo quando não forem pertinentes.
- Se faltar evidência, refine a consulta ou aumente top_k com um
  objetivo concreto, respeitando os limites da ferramenta.
- Não repita a mesma busca sem motivo.
- Se a evidência continuar insuficiente, informe a limitação ou
  use outra consulta adequada conforme as regras anteriores.

## Respostas e fidelidade

- Responda apenas com informações sustentadas pelos dados retornados.
- Para perguntas gerais, prefira um parágrafo curto.
- Uma busca semântica não garante cobertura completa da planilha.
- Em resumos com cobertura parcial, use "Nos registros consultados..."
  e não apresente a resposta como uma síntese exaustiva.
- Cite a aba e outras referências de origem quando disponíveis.
- Preserve valores como n/a; não os interprete como zero.
- Não invente valores, fontes ou consultas realizadas.
- Não liste intervalos de células e todas as colunas sem necessidade.
