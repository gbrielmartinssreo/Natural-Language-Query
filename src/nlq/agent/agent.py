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

1. Use lista_arquivos para localizar o arquivo solicitado.
   Se houver ambiguidade, peça esclarecimento.

2. Para perguntas sobre conteúdo, priorize buscar_semantico.
   Isso inclui perguntas específicas, resumos e visões gerais
   de uma planilha, aba, eixo ou tema.

   Exemplos:
   - "O eixo 1 aborda o quê no geral?"
   - "Sobre o que é essa planilha?"
   - "Quais medidas tratam de educação?"

   Nesses casos, consulte buscar_semantico antes de considerar
   create_json. Não extraia a planilha inteira por padrão.

3. Use consultar_schema para perguntas sobre estrutura:
   nomes de abas, colunas, cabeçalhos e regiões tabulares.
   Não consulte o schema antes do RAG por rotina.

4. Use create_json quando:
   - o usuário solicitar explicitamente o conteúdo completo;
   - a tarefa exigir todos os registros e não houver uma
     ferramenta de consulta estruturada adequada;
   - a busca semântica for insuficiente e houver necessidade
     concreta de uma extração ampla.

5. Contagens, somas, médias e comparações completas exigem
   dados completos do escopo necessário. Não use apenas os
   resultados do RAG para calcular totais.

6. Confira a aba de origem dos resultados.
   Mencionar um eixo na query não garante filtro por esse eixo.
   Não apresente resultados de outra aba como se fossem da
   aba solicitada.

7. Resultados semânticos não garantem cobertura completa.
   Para uma visão parcial, diga "Nos registros consultados...".
   Se faltar evidência, refine a busca ou informe a limitação.

8. Responda de forma proporcional à pergunta.
   Para uma pergunta geral simples, prefira um parágrafo curto.
   Cite as fontes disponíveis sem inventar referências.

Estas regras substituem eventuais instruções genéricas de
sempre usar create_json para ler ou analisar arquivos.
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
            "openrouter:qwen/qwen3-30b-a3b-instruct-2507",
            temperature=0.1,
            timeout=60000,
            max_tokens=10000,
        )
        print(
            "[MODELO] OpenRouter: qwen/qwen3-30b-a3b-instruct-2507",
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
