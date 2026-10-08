import json
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from nlq.agent.agent import create_nlq_agent


class ChatRequest(BaseModel):
    message: str
    thread_id: str


class LimparConversaRequest(BaseModel):
    thread_id: str


# api.py -> nlq -> src -> raiz do projeto
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

load_dotenv()

app = FastAPI()
agent, checkpointer = create_nlq_agent()


@app.get("/health")
def health():
    return {"status": "ok"}


def _ultima_planilha(result) -> dict | None:
    """Última planilha lida pelo agente na conversa (tool create_json)."""

    planilha = None

    for msg in result["messages"]:
        for tc in getattr(msg, "tool_calls", None) or []:
            nome = (
                tc.get("name")
                if isinstance(tc, dict)
                else getattr(tc, "name", None)
            )

            if nome != "create_json":
                continue

            args = (
                tc.get("args")
                if isinstance(tc, dict)
                else getattr(tc, "args", {}) or {}
            )

            if args.get("name"):
                planilha = {
                    "nome": args["name"],
                    "ext": args.get("ext"),
                }

    return planilha


@app.post("/api/chat")
def chat(request: ChatRequest):
    config = {
        "configurable": {
            "thread_id": request.thread_id,
        }
    }

    def generate():
        # Manda um primeiro chunk imediatamente.
        # Isso evita o H12 inicial do Heroku.
        yield (
            json.dumps(
                {
                    "type": "status",
                    "content": "processando",
                },
                ensure_ascii=False,
            )
            + "\n"
        )

        user_input = f"\nUser: {request.message}"

        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": user_input,
                    }
                ]
            },
            config=config,
        )

        response = result["messages"][-1].content
        planilha = _ultima_planilha(result)

        yield (
            json.dumps(
                {
                    "type": "result",
                    "response": response,
                    "planilha": planilha,
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.delete("/api/limpar-conversa")
def clear_chat(request: LimparConversaRequest):
    checkpointer.delete_thread(request.thread_id)

    return {
        "status": "ok",
    }


app.mount(
    "/",
    StaticFiles(
        directory=FRONTEND_DIR,
        html=True,
    ),
    name="frontend",
)
