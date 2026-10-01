# Implementações Possíveis

Este documento reúne ideias **fora do escopo atual** do NLQ. Nada aqui está
implementado — é um registro de evoluções candidatas, para consulta posterior.

O estado atual e a arquitetura em vigor estão em
[`architecture.md`](architecture.md) e [`agent.md`](agent.md).

---

## 1. Ferramentas de leitura e esquema

A tool de planilha atual (`create_json`) devolve o JSON da planilha inteira.
Evoluções possíveis, com uma tool por função:

| Ferramenta           | Função                                                    |
|----------------------|-----------------------------------------------------------|
| `listar_abas`        | Descreve abas/colunas disponíveis na planilha             |
| `ler_esquema`        | Retorna tipos, cabeçalhos e hierarquia de uma aba         |
| `consultar_dados`    | Executa consulta estruturada e retorna linhas/agregados   |
| `buscar_texto` (RAG) | Recupera células relevantes por similaridade              |

Motivo: planilhas grandes estouram o `max_tokens` se o JSON completo for enviado
ao LLM a cada pergunta. Descobrir esquema antes de consultar reduz o payload.
Com a tool atual, qualquer CSV já entra inteiro no contexto.

## 2. NL2SQL / RAG / AST

Estratégia evolutiva para a camada de consulta:

| Técnica  | Uso                                                     | Quando entra           |
|----------|---------------------------------------------------------|------------------------|
| `NL2SQL` | Perguntas agregáveis/relacionais sobre tabelas           | Primeira etapa         |
| `RAG`    | Perguntas semânticas sobre texto livre das células       | Quando o léxico variar |
| `AST`    | Análise estruturada/estatística sobre os dados           | Consultas complexas    |

As técnicas podem ser combinadas: recuperar candidatos via RAG e executar a
agregação via SQL/estruturada.

## 3. Validação da resposta (guarda-corpo)

Conferir se o resultado devolvido responde à pergunta, antes de responder ao
usuário. Detecta alucinação de valores e consultas que retornam vazio sem motivo.

## 4. Memória de conversa

Hoje cada pergunta é enviada isoladamente. Com `session_id`, o agente passa a
manter contexto para consultas em múltiplos turnos ("e no mês passado?").

## 5. Pontos de extensão já previstos no código

- **Registro de ferramentas** (`tools=[create_json]` em `agent.py`) — cada técnica
  de consulta vira uma tool do agente.
- **Seleção de modelo** — o modelo é parametrizável em `create_nlq_agent()`; trocar
  de LLM via OpenRouter não exige mudar o núcleo.
- **Troca de fonte de dados** — dentro do formato CSV, trocar de planilha não
  afeta o agente. Ampliar o parser para XLSX é o que destrava novas fontes.
- **Escopo do agente** — `prompts/specific_role.md` permite trocar o papel do
  agente sem alterar o núcleo.

## 6. Escala de dificuldade das planilhas

Referência para dimensionar o parser. Detalhes em
[`scale_difficulties.md`](scale_difficulties.md) — o nível 1 (CSV limpo) é o
alvo inicial; a planilha atual em `sheets/` é o nível 4 (desafio final).
