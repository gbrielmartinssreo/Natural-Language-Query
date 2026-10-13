from nlq.agent.agent import create_nlq_agent
from nlq.agent.metrics import PerfCallbackHandler
from nlq.paths import load_env

import time
import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.live import Live
from rich.spinner import Spinner
from rich.panel import Panel


DEBUG_TOOLS = True


def diagnosticar_execucao(messages):
    """Exibe chamadas e resultados das tools do turno atual."""

    inicio = 0

    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            inicio = i
            break

    mensagens_turno = messages[inicio:]

    print("\n========== DEBUG AGENT ==========")

    for msg in mensagens_turno:

        if isinstance(msg, AIMessage):

            for call in msg.tool_calls:
                print(f"\n[TOOL CALL] {call['name']}")
                print(
                    json.dumps(
                        call.get("args", {}),
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    )
                )

        elif isinstance(msg, ToolMessage):
            conteudo = str(msg.content)

            print(f"\n[TOOL RESULT] {msg.name}")
            print(f"Caracteres: {len(conteudo)}")
            print(f"Status: {msg.status}")

            if msg.name == "consultar_dados":
                print(conteudo[:3500])

    ultima = messages[-1]

    print("\n[RESPOSTA FINAL]")
    print("Tipo:", type(ultima).__name__)
    print("Conteúdo vazio:", not bool(ultima.content))

    if isinstance(ultima, AIMessage):
        print(
            "Finish reason:",
            ultima.response_metadata.get("finish_reason"),
        )
        print("Tokens:", ultima.usage_metadata)

    print("=================================\n")


def main():
    load_env()

    agent, checkpointer = create_nlq_agent()
    console = Console()

    config = {
        "configurable": {
            "thread_id": "default"
        },
        "callbacks": [],
    }

    while True:
        console.rule(style="black")

        user_input = Prompt.ask("\n[bold cyan]User[/bold cyan]")

        if user_input.lower() in ("sair", "exit", "quit"):
            console.print("\n[dim]Encerrando[/dim]")
            break

        perf = PerfCallbackHandler()
        config["callbacks"] = [perf]

        t_agent = time.perf_counter()

        with Live(
            Spinner(
                "dots",
                text="[bold blue]Pensando...[/bold blue]"
            ),
            console=console,
            refresh_per_second=10,
            transient=True,
        ):
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

        print(
            f"[PERF] agent.invoke: "
            f"{time.perf_counter() - t_agent:.2f}s"
        )

        perf.imprimir()

        mensagens = result["messages"]
        print(
            f"[PERF] contexto: {len(mensagens)} mensagens, "
            f"{sum(len(str(m.content)) for m in mensagens)} chars",
            flush=True,
        )

        if DEBUG_TOOLS:
            diagnosticar_execucao(result["messages"])

        response = result["messages"][-1].content

        if isinstance(response, list):
            response = "\n".join(
                bloco.get("text", "")
                for bloco in response
                if isinstance(bloco, dict)
                and bloco.get("type") == "text"
            )

        if not isinstance(response, str):
            response = str(response)

        if not response.strip():
            response = (
                "O agente encerrou a execução "
                "sem produzir uma resposta."
            )

        console.print(
            Panel(
                Markdown(response),
                title="[bold black]Chat[/bold black]",
                border_style="black",
                padding=(1, 2),
            )
        )


if __name__ == "__main__":
    main()
