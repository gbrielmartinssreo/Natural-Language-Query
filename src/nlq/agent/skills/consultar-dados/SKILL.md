---
name: consultar-dados
description: Use consultar_dados para consultas tabulares exatas, incluindo filtros, contagens, cálculos, rankings, agrupamentos por uma ou mais colunas e consolidação de valores distintos em CSV e XLSX.
---

# Consulta tabular com Pandas

Use `consultar_dados` quando o usuário pedir quantidade, percentuais, filtros, comparações, soma, média, máximo, mínimo, agrupamentos, ordenação ou valores distintos.

1. Resolva o arquivo via `lista_arquivos`; use `consultar_schema` somente se precisar inspecionar colunas/abas, não como rotina obrigatória.
2. Para consulta exata, invoque `consultar_dados(name, ext, operacao, ...)` com colunas existentes e filtros estruturados.
3. Operações disponíveis: `contar`, `filtrar`, `agregar`, `agrupar`, `ordenar`, `metas`, `distintos`.
4. Filtros são uma lista de objetos: `[{"coluna":"Status","operador":"igual","valor":"Concluído"}]`. Combina filtros por E (AND). Para alternativas na mesma coluna, use `em` com uma lista de valores.
5. Em `agregar`, indique `coluna` e `agregacao` (`soma`, `media`, `minimo`, `maximo`, `contagem`). Em `ordenar`, indique `ordenar_por` e `ordem` (`asc` ou `desc`). Em `agrupar`, indique `agrupar_por` e, se necessária, a coluna/operador de agregação.
6. Em perguntas por **significado** (paráfrases, conceitos), use primeiro `buscar_semantico`. Se a pergunta pedir análise apenas dos candidatos retornados, copie suas refs `{"aba":"...","indice":N}` para `refs` de `consultar_dados`.
7. **Nunca** trate os `top_k` resultados semânticos como universo completo em contagens exaustivas. Se for necessário cobrir tudo, obtenha filtros objetivos aplicáveis ao arquivo inteiro ou informe a limitação.
8. A consulta estruturada devolve linhas com `_origem` (`aba`, `indice`); cite esses identificadores como registros carregados, **não como número físico da linha do Excel**.
9. Não assuma que `n/a` representa zero, que uma célula vazia significa 0 ou que uma resposta negativa (`não`) é ausência.
10. Não use `create_json` para contagens ou agrupamentos quando `consultar_dados` resolver a pergunta.

## Seleção e eficiência

- Priorize consultar_dados para filtros,
  contagens, agrupamentos, comparações,
  ordenações e agregações exatas.
- Não execute buscar_semantico antes de
  consultar_dados quando os critérios puderem
  ser verificados diretamente nas colunas.
- Utilize múltiplos filtros para condições
  simultâneas. Os filtros são combinados por AND.
- Consulte somente as colunas necessárias.
- Reutilize resultados anteriores quando
  suficientes, evitando consultas redundantes.
- Não utilize create_json para substituir
  operações já disponíveis em consultar_dados.

## Consolidação de resultados

- Diferencie registros, medidas e valores distintos.
- Uma medida pode aparecer em vários registros.
- Quando o usuário solicitar medidas distintas,
  utilize a operação distintos na coluna adequada,
  respeitando os filtros.
- Não confunda total de registros com total de
  medidas distintas.
- Evite repetir a mesma medida desnecessariamente
  na resposta.
- Preserve informações diferentes associadas
  a registros da mesma medida.
- Para agrupar por mais de uma coluna, use
  `agrupar` com `agrupar_por` separado por vírgulas
  (ex.: `"aba, Medida"`).
- Para reunir os valores distintos associados a
  cada grupo já no Pandas, use `agrupar` com
  `agregacao="valores"` e a coluna desejada. O
  resultado traz `valores`, `total_registros` e
  `_refs`, evitando consolidar registros repetidos
  manualmente.
- Prefira uma única consulta consolidada a várias
  chamadas apenas para reorganizar os mesmos dados.

## Integridade e rastreabilidade

- Preserve os nomes e valores originais das colunas.
- Considere a aba ao interpretar cada registro.
- Utilize as referências de origem retornadas.
- Não confunda índice do registro com linha física
  do Excel.
- Se truncado=true, informe que existem resultados
  adicionais não exibidos.
- Nunca apresente resultados parciais como completos.
- Em consultas híbridas, refs restringe a execução
  aos candidatos recuperados pelo RAG.
- Não trate top_k como recuperação exaustiva.
