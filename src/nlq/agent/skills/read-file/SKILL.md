---
name: read-file
description: Use quando o usuário pedir para mostrar o conteúdo ou fazer um extração ampla de informações. Sempre use lista_arquivos primeiro para localizar o arquivo correto e obter seu caminho. Depois use create_json para extrair os dados. Se houver mais de um arquivo plausível e não for possível determinar com segurança qual o usuário deseja, peça confirmação antes de abrir.
---

# Leitura e análise de arquivos

Localize o arquivo solicitado antes de consultar seu conteúdo. Depois, selecione a ferramenta adequada à intenção da pergunta.

## Fluxo

1. Use `lista_arquivos` para localizar o arquivo.
2. Se não houver correspondência, informe que o arquivo não foi encontrado.
3. Se houver múltiplas correspondências plausíveis, peça confirmação.
4. Se houver uma correspondência clara, escolha a ferramenta de consulta apropriada.

## Escolha da ferramenta

- **Estrutura da planilha:** `consultar_schema`.
- **Busca de informações por significado:** `buscar_semantico`.
- **Extração ampla dos registros:** `create_json`, quando a pergunta realmente exigir acesso ao conjunto completo de dados.
- **Contagens, somas, filtros exatos e comparações completas:** use uma ferramenta de consulta estruturada, quando disponível.

Não use `create_json` por padrão para toda pergunta sobre conteúdo. A extração completa pode aumentar desnecessariamente o contexto enviado à LLM.

## Regras de análise

- Não invente informações que não estejam sustentadas pelos dados.
- Não considere uma busca semântica uma consulta exaustiva.
- Não responda a cálculos exatos usando apenas os primeiros resultados semânticos.
- Preserve os valores originais, incluindo `n/a`.
- Se os dados recuperados forem insuficientes, faça outra consulta ou informe a limitação.
- Não afirme ter consultado dados que nenhuma ferramenta retornou.

## Arquivos ambíguos

Se existirem várias versões ou arquivos plausíveis, peça ao usuário que escolha antes de prosseguir.
