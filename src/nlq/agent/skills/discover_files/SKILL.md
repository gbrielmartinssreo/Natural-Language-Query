---
name: discover-files
description: Use esta skill sempre que o usuário mencionar arquivos, planilhas, Excel, XLSX, XLS, CSV ou documentos disponíveis para análise. Antes de responder sobre arquivos existentes, use obrigatoriamente a tool lista_arquivos para descobrir quais arquivos estão disponíveis e obter seus caminhos reais.
---

# Descoberta de arquivos

Sempre que o pedido do usuário envolver arquivos, planilhas, Excel, XLSX, XLS ou CSV, consultar primeiro os arquivos disponíveis.

## Procedimento

1. Usar obrigatoriamente a tool `lista_arquivos`.
2. Considerar apenas os arquivos retornados pela tool.
3. Nunca assumir que um arquivo existe apenas porque o usuário mencionou um nome.
4. Nunca inventar caminhos.
5. Usar os caminhos retornados por `lista_arquivos` como fonte de verdade.

## Regras

- Se o usuário mencionar um nome parcial de arquivo, procurar correspondências na saída de `lista_arquivos`.
- Se existir uma única correspondência clara, utilizar esse arquivo.
- Se existirem múltiplas correspondências plausíveis, não escolher arbitrariamente.
- Se nenhum arquivo corresponder ao pedido, informar que ele não foi encontrado.
