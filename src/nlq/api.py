from turtle import clear

from fastapi import FastAPI

from nlq.agent.agent import create_nlq_agent
from dotenv import load_dotenv

app = FastAPI()
load_dotenv()
agent, checkpointer = create_nlq_agent()

@app.get("/")
async def read_root():
    return {"Hello": "World"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/chat")
def chat(request:str):

    config = {
        "configurable": {
            "thread_id": "default"
        }
    }

    user_input = (f"\nUser: {request}")
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

    return {"response": response}

@app.delete("/api/limpar-conversa")
def clear_chat():
    checkpointer.delete_thread("default")

    return {
        "status": "ok"
    }
