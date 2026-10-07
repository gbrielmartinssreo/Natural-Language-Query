from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from nlq.agent.agent import create_nlq_agent

# api.py -> nlq -> src -> raiz do projeto
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI()
load_dotenv()
agent, checkpointer = create_nlq_agent()


import os

@app.get("/debug/env")
def debug_env():
    return {
        "groq": bool(os.getenv("GROQ_API_KEY")),
        "openrouter": bool(os.getenv("OPENROUTER_API_KEY")),
        "api_select": os.getenv("API_SELECT"),
    }

@app.get("/health")
def health():
    return {"status": "ok"}


def _ultima_planilha(result) -> dict | None:
    """Última planilha lida pelo agente na conversa (tool create_json)."""
    planilha = None
    for msg in result["messages"]:
        for tc in getattr(msg, "tool_calls", None) or []:
            nome = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
            if nome != "create_json":
                continue
            args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {}) or {}
            if args.get("name"):
                planilha = {"nome": args["name"], "ext": args.get("ext")}
    return planilha


@app.post("/api/chat")
def chat(request: str):
    config = {"configurable": {"thread_id": "default"}}

    user_input = f"\nUser: {request}"
    result = agent.invoke(
        {"messages": [{"role": "user", "content": user_input}]},
        config=config,
    )

    response = result["messages"][-1].content
    return {"response": response, "planilha": _ultima_planilha(result)}


@app.delete("/api/limpar-conversa")
def clear_chat():
    checkpointer.delete_thread("default")
    return {"status": "ok"}


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
