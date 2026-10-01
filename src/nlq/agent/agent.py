from langchain.agents import create_agent
from langchain.chat_models import init_chat_model

import os
import requests
from pathlib import Path
from dotenv import load_dotenv


from nlq.tools.extract import create_json

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent

def load_prompt(path:str)->str:
   return (BASE_DIR / path).read_text(encoding="utf-8")


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

        status = response.status_code

        return status == 200

    except requests.RequestException:
        return False


def create_nlq_agent():

    model1 = init_chat_model(
            "openai/gpt-oss-120b",
            model_provider="groq",
            temperature=0.1,
            timeout=60000,
            max_tokens=500,
        )


    model2 = init_chat_model(
        "openrouter:qwen/qwen3-30b-a3b-instruct-2507",
        temperature=0.1,
        timeout=60000,
        max_tokens=500,
    )


    if os.getenv("API_SELECT") == "groq" or not check_openrouter_key():
        model = model1
    elif os.getenv("API_SELECT") == "openrouter" or check_openrouter_key():
        model = model2

    tools = [create_json]

    return create_agent(
        model=model,
        tools=tools,
        system_prompt=(load_prompt("prompts/system_base.md")+"\n\n"+load_prompt("prompts/sejus.md")),
    )
