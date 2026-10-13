---
name: buscar-semantico
description: Use buscar_semantico apenas quando a pergunta depender de significado, sinônimos ou interpretação conceitual de um tema, e não quando os critérios puderem ser verificados diretamente nas colunas (nesse caso, use consultar_dados).
---

# Busca semântica em planilhas

A ferramenta `buscar_semantico` recupera os registros mais relacionados semanticamente a uma consulta, usando embeddings.

Ela retorna os trechos encontrados, suas abas de origem e suas pontuações de similaridade.

## Quando usar

- Relacionar um tema a registros usando significado, sinônimos ou paráfrases.
- Localizar registros cujas palavras diferem das utilizadas na planilha.
- Interpretar uma necessidade descrita em linguagem natural sem termos exatos.
- Descobrir quais registros são conceitualmente relevantes para uma pergunta aberta.

## Quando não usar como única ferramenta

- Contagens completas de registros.
- Somas, médias ou cálculos.
- Comparações que exijam todos os registros.
- Perguntas que dependam de garantir que nenhum registro relevante foi omitido.

Nesses casos, use uma ferramenta de consulta estruturada, se disponível. Não trate os resultados semânticos como uma amostra completa da planilha.

## Como chamar

`buscar_semantico(name, ext, query, top_k=5)`

- `name`: nome do arquivo sem extensão.
- `ext`: extensão do arquivo.
- `query`: descrição do assunto ou informação procurada.
- `top_k`: quantidade máxima de resultados desejados.

Comece com poucos resultados e aumente `top_k` quando precisar de maior cobertura.

## Como responder

1. Leia os registros retornados.
2. Identifique quais realmente respondem à pergunta.
3. Baseie afirmações e números nos campos presentes nos registros.
4. Diferencie metas nacionais de metas estaduais e valores por ano.
5. Preserve valores como `n/a`; eles não significam zero.
6. Não apresente a pontuação de similaridade como probabilidade de acerto.
7. Não invente iniciativas, metas, indicadores ou quantidades.
8. Se os resultados não forem suficientes, faça outra busca mais específica ou informe a limitação.

## Regra importante

A busca semântica encontra registros relevantes, mas não garante que todos os registros relevantes tenham sido recuperados.

## Prioridade e economia de chamadas

- Use buscar_semantico quando a pergunta exigir
  interpretação de significado, conceitos,
  sinônimos ou relações semânticas.
- Não utilize RAG como etapa obrigatória antes
  de consultar_dados.
- Se a pergunta envolver condições verificáveis
  diretamente nas colunas, prefira consultar_dados.
- Não utilize RAG para contagens, rankings ou
  agregações exaustivas.
- Comece com top_k=5 e aumente somente quando
  houver necessidade de mais evidências.
- Não repita buscas que já forneceram informações
  suficientes.
- Não trate os resultados recuperados como
  representação completa da planilha.
- Se uma consulta exigir semântica e cálculo,
  combine buscar_semantico e consultar_dados,
  respeitando as limitações de cobertura.
- Preserve as referências e abas dos registros.
- Responda proporcionalmente ao pedido.
