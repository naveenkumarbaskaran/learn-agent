"""Command-line interface for learn-agent."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

from .agent import LearnAgent
from .spaced_rep import load_deck, get_due_cards

console = Console()


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(package_name="learn-agent-ai")
def cli() -> None:
    """Learn Agent -- AI-powered adaptive learning with spaced repetition."""


# ---------------------------------------------------------------------------
# study command
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("topic_or_file")
@click.option(
    "--deck",
    default="deck.json",
    show_default=True,
    metavar="PATH",
    help="Path to the JSON deck file.",
)
@click.option(
    "--api-key",
    envvar="ANTHROPIC_API_KEY",
    default=None,
    help="Anthropic API key (falls back to ANTHROPIC_API_KEY env var).",
)
def study(topic_or_file: str, deck: str, api_key: str | None) -> None:
    """
    Generate flashcards for TOPIC_OR_FILE and add them to DECK.

    TOPIC_OR_FILE can be:
      - A plain topic description (e.g. "photosynthesis")
      - A path to a Markdown or text file
    """
    agent = LearnAgent(api_key=api_key)

    is_file = Path(topic_or_file).exists() and Path(topic_or_file).is_file()
    label = Path(topic_or_file).name if is_file else topic_or_file

    with console.status(f"[bold cyan]Generating flashcards for '{label}'..."):
        try:
            new_cards = agent.study(topic_or_file, deck_path=deck)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Error:[/red] {exc}")
            sys.exit(1)

    if not new_cards:
        console.print("[yellow]No new cards were generated (all duplicates?).[/yellow]")
        return

    table = Table(title=f"Generated {len(new_cards)} new card(s)", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Question", style="bold")
    table.add_column("Answer", style="green")
    table.add_column("Tags", style="cyan")

    for i, card in enumerate(new_cards, 1):
        table.add_row(
            str(i),
            card.question,
            card.answer,
            ", ".join(card.tags) if card.tags else "-",
        )

    console.print(table)
    console.print(f"\n[bold green]Deck saved to:[/bold green] {deck}")


# ---------------------------------------------------------------------------
# quiz command
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--deck",
    default="deck.json",
    show_default=True,
    metavar="PATH",
    help="Path to the JSON deck file.",
)
@click.option(
    "--max-cards",
    default=20,
    show_default=True,
    type=int,
    help="Maximum number of cards to review per session.",
)
@click.option(
    "--api-key",
    envvar="ANTHROPIC_API_KEY",
    default=None,
    help="Anthropic API key (falls back to ANTHROPIC_API_KEY env var).",
)
def quiz(deck: str, max_cards: int, api_key: str | None) -> None:
    """
    Run an interactive quiz session for due cards in DECK.
    """
    if not Path(deck).exists():
        console.print(f"[red]Deck file not found:[/red] {deck}")
        console.print("Run [bold]learn-agent study <topic>[/bold] first.")
        sys.exit(1)

    due = get_due_cards(deck)
    if not due:
        all_cards = load_deck(deck)
        if not all_cards:
            console.print("[yellow]Deck is empty. Run 'study' first.[/yellow]")
        else:
            next_due = min(all_cards, key=lambda c: c.due_date)
            console.print(
                f"[green]No cards due today![/green] "
                f"Next review: [bold]{next_due.due_date}[/bold]"
            )
        return

    session_count = min(len(due), max_cards)
    console.print(
        Panel(
            f"[bold cyan]Quiz Session[/bold cyan]\n"
            f"Due: [yellow]{len(due)}[/yellow] cards  |  "
            f"Reviewing: [yellow]{session_count}[/yellow]  |  "
            f"Deck: [dim]{deck}[/dim]",
            expand=False,
        )
    )

    agent = LearnAgent(api_key=api_key)

    def _prompt(prompt_str: str) -> str:
        return console.input(f"[bold]{prompt_str}[/bold]")

    try:
        summary = agent.quiz(
            deck_path=deck,
            max_cards=max_cards,
            console_callback=_prompt,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Quiz interrupted.[/yellow]")
        return
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Error during quiz:[/red] {exc}")
        sys.exit(1)

    console.print(
        Panel(
            f"[bold]Session complete[/bold]\n"
            f"Reviewed: {summary['reviewed']}  |  "
            f"[green]Correct: {summary['correct']}[/green]  |  "
            f"[red]Incorrect: {summary['incorrect']}[/red]",
            title="Results",
            expand=False,
        )
    )


# ---------------------------------------------------------------------------
# add command
# ---------------------------------------------------------------------------

@cli.command(name="add")
@click.argument("question")
@click.argument("answer")
@click.option(
    "--deck",
    default="deck.json",
    show_default=True,
    metavar="PATH",
    help="Path to the JSON deck file.",
)
@click.option(
    "--tags",
    default="",
    help="Comma-separated list of tags (e.g. 'biology,cell').",
)
def add_card(question: str, answer: str, deck: str, tags: str) -> None:
    """
    Manually add a flashcard with QUESTION and ANSWER to DECK.

    Example:

      learn-agent add "What is mitosis?" "Cell division producing two identical daughter cells" --deck deck.json
    """
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    # LearnAgent.add_card does not need a live API connection
    agent = LearnAgent()
    card = agent.add_card(
        question=question,
        answer=answer,
        deck_path=deck,
        tags=tag_list,
    )

    console.print(f"[green]Card added to {deck}[/green]")
    console.print(f"  Q: {card.question}")
    console.print(f"  A: {card.answer}")
    if card.tags:
        console.print(f"  Tags: {', '.join(card.tags)}")


# ---------------------------------------------------------------------------
# stats command (bonus)
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--deck",
    default="deck.json",
    show_default=True,
    metavar="PATH",
    help="Path to the JSON deck file.",
)
def stats(deck: str) -> None:
    """Show statistics for a deck."""
    if not Path(deck).exists():
        console.print(f"[red]Deck file not found:[/red] {deck}")
        sys.exit(1)

    all_cards = load_deck(deck)
    due_cards = [c for c in all_cards if c.is_due]
    future_cards = [c for c in all_cards if not c.is_due]
    new_cards = [c for c in all_cards if c.repetitions == 0]
    mature_cards = [c for c in all_cards if c.interval >= 21]

    table = Table(title=f"Deck statistics: {deck}", show_header=True)
    table.add_column("Metric", style="bold")
    table.add_column("Value", style="cyan", justify="right")

    table.add_row("Total cards", str(len(all_cards)))
    table.add_row("Due today", str(len(due_cards)))
    table.add_row("Upcoming", str(len(future_cards)))
    table.add_row("New (never reviewed)", str(len(new_cards)))
    table.add_row("Mature (interval >= 21d)", str(len(mature_cards)))

    if future_cards:
        next_due = min(future_cards, key=lambda c: c.due_date)
        table.add_row("Next review date", next_due.due_date)

    console.print(table)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    cli()


if __name__ == "__main__":
    main()
