---
name: list-files
description: Use esta skill quando o usuário pedir para listar, mostrar, exibir, ver ou descobrir quais arquivos, planilhas, CSVs, Excels ou documentos estão disponíveis. Use lista_arquivos e organize a resposta por pasta e formato de arquivo.
---

# Listagem de arquivos disponíveis

Apresentar os arquivos disponíveis de forma organizada e legível.

## Procedimento

1. Usar a tool `lista_arquivos`.
2. Ler os arquivos e caminhos retornados.
3. Agrupar os resultados por pasta.
4. Dentro de cada pasta, agrupar ou identificar os arquivos por extensão.
5. Exibir nomes de arquivos de forma clara.
6. Não mostrar informações técnicas desnecessárias.

## Formatação

Preferir estrutura semelhante a:

### CSV

`financeiro/`
- despesas.csv
- receitas.csv

`faculdade/`
- alunos.csv
- notas.csv

### XLSX

`financeiro/`
- controle_mensal.xlsx

`faculdade/`
- semestre_2026.xlsx

## Regras

- Não inventar arquivos.
- Não alterar nomes.
- Não ocultar a extensão.
- Não exibir caminhos absolutos internos desnecessariamente.
- Mostrar a pasta relativa quando ela ajudar o usuário a diferenciar arquivos.
