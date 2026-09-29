from nlq.agent.agent import create_nlq_agent
from dotenv import load_dotenv
import os


def main():
    load_dotenv()

    agent = create_nlq_agent()

    while True:
        user_input = input("User: ")

        if(user_input=="sair" or user_input=="exit" or user_input=="quit"):
            print("\nEncerrando")
            break

        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": user_input,
                    }
                ]
            }
        )

        print("Chat: " + result["messages"][-1].content)
