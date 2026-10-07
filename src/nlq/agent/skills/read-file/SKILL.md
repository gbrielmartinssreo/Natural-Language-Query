---
name: read-file
description: Use esta skill quando o usuário pedir para abrir, ler, mostrar o conteúdo, consultar, analisar, resumir, comparar ou extrair informações de um arquivo, planilha, Excel, XLSX, XLS ou CSV. Sempre use lista_arquivos primeiro para localizar o arquivo correto e obter seu caminho. Depois use create_json para extrair os dados. Se houver mais de um arquivo plausível e não for possível determinar com segurança qual o usuário deseja, peça confirmação antes de abrir.
---

# Leitura e análise de arquivos

Para qualquer operação que dependa do conteúdo de um arquivo, localizar primeiro o arquivo correto e somente depois extrair seus dados.

## Fluxo obrigatório

1. Usar `lista_arquivos`.
2. Procurar o arquivo solicitado nos resultados.
3. Se nenhum arquivo corresponder:
   - não usar `create_json`;
   - informar que o arquivo não foi encontrado;
   - mostrar correspondências semelhantes, se existirem;
   - aguardar o usuário indicar um arquivo válido.
4. Se houver múltiplas correspondências plausíveis:
   - não escolher arbitrariamente;
   - mostrar as opções;
   - pedir confirmação.
5. Se houver uma única correspondência clara:
   - obter o caminho;
   - usar `create_json`;
   - continuar a leitura ou análise.

## Regras de identificação

Considere correspondência clara quando:

- o nome informado corresponder exatamente a um arquivo;
- houver apenas um arquivo cujo nome seja compatível com o pedido;
- o contexto da conversa identificar inequivocamente o arquivo.

Considere correspondência ambígua quando:

- houver arquivos com nomes semelhantes;
- houver versões diferentes do mesmo arquivo;
- houver o mesmo nome em pastas diferentes;
- o usuário usar uma descrição genérica que possa indicar mais de um arquivo.

## Regras de segurança

- Nunca inventar o caminho de um arquivo.
- Nunca chamar `create_json` antes de localizar o arquivo com `lista_arquivos`.
- Nunca analisar conteúdo sem antes extraí-lo com `create_json`.
- Não assumir qual arquivo o usuário quis dizer quando houver ambiguidade.
- Não alegar ter lido um arquivo se `create_json` não tiver sido utilizado com sucesso.

## Quando o arquivo não for encontrado

Após usar `lista_arquivos`, se nenhum arquivo corresponder ao pedido do usuário:

1. Não chamar `create_json`.
2. Não inventar caminhos ou nomes de arquivos.
3. Informar claramente que o arquivo solicitado não foi encontrado.
4. Se existirem arquivos com nomes parecidos, mostrar apenas as opções mais prováveis.
5. Se não houver nenhuma opção parecida, informar que não há correspondência entre os arquivos disponíveis.
6. Se o usuário tiver informado apenas parte do nome, permitir que ele escolha entre as correspondências encontradas.
7. Somente continuar a leitura após o usuário indicar ou confirmar um arquivo válido.

## Exemplo

Usuário:
"abre a planilha de vendas"

Resultado de `lista_arquivos`:
- financeiro.xlsx
- vendas_2025.csv
- vendas_2026.csv

Comportamento:
- não escolher automaticamente entre `vendas_2025.csv` e `vendas_2026.csv`;
- mostrar as duas opções;
- pedir confirmação do usuário.

Se o resultado for:
- financeiro.xlsx
- alunos.csv

Comportamento:
- informar que nenhuma planilha de vendas foi encontrada;
- não chamar `create_json`.
