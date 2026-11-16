---
name: gerar-grafico
description: Use gerar_grafico para visualizar dados ou análises, escolhendo métricas relevantes e reutilizando resultados já consultados.
---

# Gerar gráficos

Quando o usuário solicitar um gráfico, use gerar_grafico.
Não substitua o gráfico por barras de texto, tabela ou código Mermaid.

Antes de gerar:
- Identifique dimensão, medida, agregação e filtros.
- Para distribuições numéricas, use intervalos calculados pela ferramenta
  de consulta quando houver suporte. Não invente parâmetros nem apresente
  valores individuais como faixas. Se não houver suporte, informe a limitação.
- Preserve a ordem numérica de intervalos e a ordem cronológica de períodos.
- Use rankings por valor apenas quando isso fizer sentido para a pergunta.
- Confira truncado antes de representar o resultado como completo.

## Escolher as entradas

- Priorize a métrica pedida; em “gráfico dessa análise”, represente sua conclusão principal.
- Escolha uma comparação e execute, sem explorar métricas extras.
- Use categorias legíveis e valores do mesmo escopo, período e filtros.
- Não misture unidades diferentes no mesmo eixo.
- Use múltiplas séries apenas para comparar a mesma métrica entre grupos.
- Preserve dados ausentes; não substitua por zero.

## Escolher o tipo

- bar: comparar categorias, médias ou rankings.
- line: evolução temporal, com períodos em ordem.
- pie ou doughnut: partes de um total, com poucas categorias.
- Não use pizza para médias nem linhas para categorias independentes.

## Consultar e gerar

1. Reutilize resultados suficientes das ferramentas.
2. Consulte somente o que faltar com consultar_dados.
3. Para valores por categoria, use operacao="agrupar" e a agregação adequada.
4. Confira se o retorno contém cada grupo, não apenas o total geral.
5. Chame gerar_grafico com tipo, titulo, rotulos, series e fonte.

Mantenha valores alinhados aos rótulos e informe unidade, agregação e filtros.
Não invente números nem trate resultados parciais do RAG como totais completos.
Não liste arquivos ou consulte schema quando essas informações já estiverem disponíveis.
Se uma chamada falhar, corrija a causa antes de repetir.

## Finalizar

Após sucesso, explique brevemente o resultado e encerre.
Não repita consultas, gere variações ou copie JSON sem solicitação.
Gere exatamente um gráfico por solicitação, salvo pedido explícito
de múltiplos gráficos.
Após gerar_grafico retornar sucesso, encerre as chamadas de ferramentas
e responda com uma frase curta descrevendo a visualização escolhida.
Não interprete a mensagem original novamente como um novo pedido
após o retorno da ferramenta.
O gráfico é renderizado pela interface a partir do resultado da tool.
Não gere Markdown de imagem, URLs, base64 ou imagens fictícias.
Não afirme que o gráfico foi gerado se a ferramenta retornar erro.
