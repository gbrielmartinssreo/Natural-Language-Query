from nlq.agent.agent import create_nlq_agent
from dotenv import load_dotenv

from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.live import Live
from rich.spinner import Spinner
from rich.panel import Panel
from rich.rule import Rule


def main():
    load_dotenv()

    agent = create_nlq_agent()
    console = Console()

    config = {
        "configurable": {
            "thread_id": "default"
        }
    }

    while True:
        console.rule(style="black")

        user_input = Prompt.ask("\n[bold cyan]User[/bold cyan]")

        if user_input.lower() in ("sair", "exit", "quit"):
            console.print("\n[dim]Encerrando[/dim]")
            break

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

                config=config
            )

        response = result["messages"][-1].content

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
