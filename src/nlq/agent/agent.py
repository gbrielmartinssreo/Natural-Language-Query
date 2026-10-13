from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import InMemorySaver

import os
import requests

from nlq.paths import load_env, prompts_dir, skills_dir
from nlq.tools.extract import create_json
from nlq.tools.dev_master import goat
from nlq.tools.listar_planilhas import lista_arquivos
from nlq.tools.schema_info import consultar_schema
from nlq.tools.retrieval import buscar_semantico
from nlq.tools.consultar_dados import consultar_dados


load_env()


def load_prompt(name: str) -> str:
    return (prompts_dir() / name).read_text(encoding="utf-8")


def check_openrouter_key() -> bool:
    key = os.getenv("OPENROUTER_API_KEY")

    if not key:
        return False

    try:
        response = requests.get(
            "https://openrouter.ai/api/v1/key",
            headers={
                "Authorization": f"Bearer {key}",
            },
            timeout=5,
        )

        return response.status_code == 200

    except requests.RequestException:
        return False


REGRAS_DE_CONSULTA = """
Escolha das ferramentas para consultar arquivos:

1. IDENTIFICAÇÃO DO ARQUIVO
   - Use lista_arquivos para descobrir arquivos disponíveis.
   - Se o arquivo já estiver identificado na conversa, reutilize-o.
   - Se houver ambiguidade real, solicite esclarecimento.
   - Não repita a descoberta sem necessidade.

2. ESCOLHA DA ESTRATÉGIA
   Identifique a natureza da pergunta antes de selecionar ferramentas.

   Use consultar_dados quando a consulta puder ser resolvida
   por operações determinísticas sobre colunas e registros:
   - filtros e condições;
   - contagens e percentuais;
   - somas, médias, mínimos e máximos;
   - comparações e rankings;
   - agrupamentos e valores distintos;
   - identificação de registros com múltiplos critérios.

   Use buscar_semantico quando a consulta exigir:
   - interpretação de significado;
   - relações conceituais;
   - identificação de sinônimos;
   - recuperação de registros por similaridade;
   - perguntas abertas que não possam ser resolvidas
     por correspondência direta dos dados.

   Não utilize RAG como etapa obrigatória antes do Pandas.
   Não utilize ambas as ferramentas por rotina.

3. CONSULTAS ESTRUTURADAS
   - Prefira consultar_dados para condições verificáveis
     diretamente nos valores das colunas.
   - Combine múltiplos filtros na mesma chamada quando
     a pergunta exigir condições simultâneas (AND).
   - Consulte apenas as colunas necessárias.
   - Se a consulta envolver todas as abas, não execute
     uma chamada para cada aba sem necessidade.
   - Use aba="" para consultar todas as abas quando
     a estrutura permitir.
   - Respeite os limites e indicadores de truncamento.

4. CONSULTAS SEMÂNTICAS
   - Utilize buscar_semantico somente quando houver
     necessidade real de recuperação por significado.
   - Comece com poucos candidatos e amplie quando necessário.
   - Similaridade não representa certeza ou relevância
     garantida.
   - Resultados top_k não representam cobertura exaustiva.
   - Não calcule totais completos com base apenas
     nos candidatos recuperados.

5. CONSULTAS HÍBRIDAS
   - Combine RAG e Pandas somente quando a pergunta
     exigir simultaneamente interpretação semântica
     e operações estruturadas.
   - Use o RAG para identificar candidatos.
   - Utilize as referências desses candidatos em
     consultar_dados para executar operações exatas.
   - Resultados calculados sobre refs representam
     somente os registros recuperados.
   - Não apresente agregações semânticas parciais
     como totais exaustivos.
   - Quando a cobertura completa não puder ser
     garantida, informe essa limitação.

6. CONSULTA DE ESTRUTURA
   - Use consultar_schema para identificar abas,
     colunas, cabeçalhos e regiões tabulares.
   - Consulte o schema quando houver dúvida real
     sobre a estrutura necessária à operação.
   - Não consulte o schema por rotina antes de
     buscar_semantico ou consultar_dados.
   - Reutilize informações estruturais já conhecidas.

7. EXTRAÇÃO COMPLETA
   Use create_json somente quando:
   - o usuário solicitar explicitamente os dados completos;
   - a tarefa exigir registros que não possam ser obtidos
     pelas ferramentas de consulta disponíveis;
   - houver necessidade justificada de extração ampla.

   Não use create_json como substituto de consultar_dados.
   Evite enviar grandes volumes de dados ao modelo.

8. EFICIÊNCIA DAS CHAMADAS
   - Planeje a consulta antes de executar ferramentas.
   - Prefira uma consulta suficiente a várias consultas
     fragmentadas que produzam o mesmo resultado.
   - Não repita chamadas com os mesmos argumentos
     quando já houver resultados suficientes.
   - Não execute ferramentas adicionais apenas para
     confirmar resultados determinísticos válidos,
     salvo quando existir inconsistência concreta.
   - Se a resposta já estiver fundamentada, finalize-a.

9. INTEGRIDADE E CONSOLIDAÇÃO
   - Diferencie registros, medidas e valores distintos.
   - Não confunda quantidade de linhas com quantidade
     de entidades únicas.
   - Quando solicitado, consolide registros repetidos
     pela chave lógica adequada à pergunta.
   - Preserve diferenças relevantes entre registros.
   - Não elimine informações distintas apenas porque
     dois registros possuem o mesmo nome.
   - Não inclua registros que deixem de satisfazer
     qualquer condição obrigatória da pergunta.
   - Nunca invente resultados ou complete dados ausentes.

10. RASTREABILIDADE
   - Preserve nomes e valores originais das fontes.
   - Confira as abas e referências dos registros.
   - Não atribua registros a abas diferentes da origem.
   - Não confunda índice lógico com linha física do Excel.
   - Não afirme que um valor está transcrito integralmente
     quando houver truncamento.
   - Se o resultado for parcial, informe a limitação.

11. CONSTRUÇÃO DA RESPOSTA
   - Responda diretamente ao que foi perguntado.
   - Evite repetir informações idênticas.
   - Organize resultados extensos de maneira legível.
   - Apresente todas as correspondências necessárias
     quando a pergunta exigir uma consulta completa.
   - Não omita resultados válidos silenciosamente.
   - Não transforme uma consulta simples em uma
     análise extensa sem necessidade.
   - Cite as fontes disponíveis sem inventar referências.

Estas regras prevalecem sobre instruções genéricas
que determinem o uso obrigatório de RAG, schema
ou extração completa antes de qualquer consulta.
"""

def create_nlq_agent():
    checkpointer = InMemorySaver()

    usar_groq = (
        os.getenv("API_SELECT", "").strip().lower() == "groq"
        or not check_openrouter_key()
    )

    if usar_groq:
        model = init_chat_model(
            "openai/gpt-oss-120b",
            model_provider="groq",
            temperature=0.1,
            timeout=60,
            max_tokens=7000,
        )
        print("[MODELO] Groq: openai/gpt-oss-120b", flush=True)

    else:
        model = init_chat_model(
            "openrouter:deepseek/deepseek-v4-flash-0731",
            temperature=0.1,
            timeout=60000,
            max_tokens=10000,
        )
        print(
            "[MODELO] OpenRouter: deepseek/deepseek-v4-flash-latest-0731",
            flush=True,
        )

    pasta_skills = skills_dir().resolve()
    arquivos_skills = sorted(pasta_skills.glob("*/SKILL.md"))

    if not arquivos_skills:
        raise RuntimeError(
            "Nenhuma skill encontrada. Esperado: "
            f"{pasta_skills}/nome-da-skill/SKILL.md"
        )

    print(f"[SKILLS] Pasta: {pasta_skills}", flush=True)

    for arquivo in arquivos_skills:
        print(
            f"[SKILLS] Encontrada no disco: {arquivo.parent.name}",
            flush=True,
        )

    # A raiz virtual "/" corresponde somente à pasta das skills.
    # Este backend permite leitura e escrita nessa pasta.
    backend = FilesystemBackend(
        root_dir=str(pasta_skills),
        virtual_mode=True,
    )

    tools = [
        create_json,
        goat,
        lista_arquivos,
        consultar_schema,
        buscar_semantico,
        consultar_dados,
    ]

    system_prompt = "\n\n".join(
        [
            load_prompt("system_base.md"),
            load_prompt("specific_role.md"),
            REGRAS_DE_CONSULTA,
        ]
    )

    agent = create_deep_agent(
        model=model,
        tools=tools,
        checkpointer=checkpointer,
        system_prompt=system_prompt,
        backend=backend,
        skills=["/"],
    )

    return agent, checkpointer
