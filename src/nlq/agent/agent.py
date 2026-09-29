from langchain.agents import create_agent
from langchain.chat_models import init_chat_model

def create_nlq_agent():
    model = init_chat_model(
        "openrouter:qwen/qwen3-30b-a3b-instruct-2507",
        temperature=0.1,
        timeout=60000,
        max_tokens=500,
    )

    return create_agent(
        model=model,
        tools=[],
        system_prompt="Você é um assistente útil e objetivo.",
    )
