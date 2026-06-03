"""LearnAgent: AI-powered adaptive learning using the Anthropic SDK."""

from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import List, Optional

import anthropic
from anthropic import beta_tool

from .spaced_rep import Card, SpacedRepetition, load_deck, save_deck, get_due_cards


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@beta_tool
def read_file(path: str) -> str:
    """
    Read the contents of a text or markdown file from disk.

    Args:
        path (str): Absolute or relative path to the file to read.

    Returns:
        str: The raw text contents of the file.
    """
    target = Path(path)
    if not target.exists():
        return f"ERROR: File not found: {path}"
    if not target.is_file():
        return f"ERROR: Path is not a file: {path}"
    try:
        return target.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return f"ERROR reading file: {exc}"


@beta_tool
def write_file(path: str, content: str) -> str:
    """
    Write content to a file on disk, creating parent directories as needed.

    Args:
        path (str): Absolute or relative path where the file should be written.
        content (str): The text content to write.

    Returns:
        str: A confirmation message or an error description.
    """
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"OK: wrote {len(content)} characters to {path}"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR writing file: {exc}"


@beta_tool
def get_due_cards_tool(deck_path: str) -> str:
    """
    Return the flashcards that are due for review from a JSON deck file.

    Args:
        deck_path (str): Path to the deck JSON file.

    Returns:
        str: A JSON-serialised list of due card objects.
    """
    cards = get_due_cards(deck_path)
    return json.dumps([c.to_dict() for c in cards], indent=2)


# Rename so the Anthropic tool name matches the public API contract
get_due_cards_tool.__name__ = "get_due_cards"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# LearnAgent
# ---------------------------------------------------------------------------

class LearnAgent:
    """
    Adaptive learning agent powered by Claude.

    Workflow
    --------
    1. ``study(topic_or_path, deck_path)``
       - Load or read a topic / document and ask Claude to generate flashcards.
       - Cards are saved to *deck_path* as a JSON deck.

    2. ``quiz(deck_path, max_cards)``
       - Load due cards from *deck_path*.
       - For each card, prompt the user, evaluate the answer with Claude, and
         apply SM-2 scheduling.
       - Updated cards are written back to *deck_path*.
    """

    MODEL = "claude-sonnet-4-6"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        )
        self._sr = SpacedRepetition()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def study(self, topic_or_path: str, deck_path: str = "deck.json") -> List[Card]:
        """
        Generate flashcards for *topic_or_path* and persist them.

        If *topic_or_path* looks like a file path and the file exists the agent
        will read it via the ``read_file`` tool; otherwise it treats the input
        as a plain topic string.

        Returns the list of newly generated :class:`Card` objects.
        """
        existing_cards = load_deck(deck_path)
        existing_questions = {c.question for c in existing_cards}

        system_prompt = (
            "You are an expert tutor and knowledge organiser. "
            "Your job is to create high-quality, atomic flashcards that help "
            "learners understand and retain key concepts. "
            "Each card should cover ONE idea and use clear, concise language.\n\n"
            "When the user gives you a topic or document you must:\n"
            "1. Identify the most important concepts, facts, and relationships.\n"
            "2. Create 8-15 flashcards covering those concepts.\n"
            "3. Respond ONLY with a valid JSON array of objects, each with keys "
            "\"question\" (string), \"answer\" (string), and \"tags\" (array of strings).\n"
            "Do not include any other prose or markdown fences."
        )

        # Determine whether to pass raw topic or let Claude read the file
        is_file = Path(topic_or_path).exists() and Path(topic_or_path).is_file()
        if is_file:
            user_message = (
                f"Please read the file at path '{topic_or_path}' using the "
                "read_file tool and then generate flashcards covering its key "
                "concepts."
            )
        else:
            user_message = (
                f"Generate flashcards for the following topic:\n\n{topic_or_path}"
            )

        messages = [{"role": "user", "content": user_message}]

        # Run the tool loop until Claude produces the final JSON answer
        response_text = self._run_tool_loop(system_prompt, messages)

        # Parse the JSON produced by Claude
        new_cards = self._parse_cards_json(response_text, existing_questions)

        all_cards = existing_cards + new_cards
        save_deck(all_cards, deck_path, topic=topic_or_path)
        return new_cards

    def quiz(
        self,
        deck_path: str = "deck.json",
        max_cards: int = 20,
        console_callback=None,
    ) -> dict:
        """
        Run an interactive quiz session for due cards.

        Parameters
        ----------
        deck_path:
            Path to the deck JSON file.
        max_cards:
            Maximum number of cards to review in this session.
        console_callback:
            Optional callable used to get user input.  Receives the prompt
            string and returns the user's answer string.  When *None* the
            built-in ``input()`` is used (suitable for CLI usage).

        Returns
        -------
        A summary dict with keys ``reviewed``, ``correct``, ``incorrect``.
        """
        if console_callback is None:
            console_callback = input

        all_cards = load_deck(deck_path)
        due = [c for c in all_cards if c.is_due]
        random.shuffle(due)
        session_cards = due[:max_cards]

        if not session_cards:
            return {"reviewed": 0, "correct": 0, "incorrect": 0,
                    "message": "No cards due for review."}

        reviewed = 0
        correct = 0
        incorrect = 0

        for card in session_cards:
            reviewed += 1
            # Show question
            print(f"\n{chr(9472) * 60}")
            print(f"Q: {card.question}")
            user_answer = console_callback("Your answer: ").strip()

            # Let Claude evaluate the answer
            quality, feedback = self._evaluate_answer(
                card.question, card.answer, user_answer
            )

            print(f"Correct answer: {card.answer}")
            print(f"Feedback: {feedback}")

            if quality >= 3:
                correct += 1
                print("Result: Correct")
            else:
                incorrect += 1
                print("Result: Incorrect")

            # Apply SM-2
            updated_card = self._sr.review(card, quality)
            # Propagate back into all_cards list
            for i, c in enumerate(all_cards):
                if c.question == updated_card.question:
                    all_cards[i] = updated_card
                    break

        save_deck(all_cards, deck_path)
        return {
            "reviewed": reviewed,
            "correct": correct,
            "incorrect": incorrect,
        }

    def add_card(
        self,
        question: str,
        answer: str,
        deck_path: str = "deck.json",
        tags: Optional[List[str]] = None,
    ) -> Card:
        """Manually add a card to the deck and persist."""
        all_cards = load_deck(deck_path)
        card = Card(question=question, answer=answer, tags=tags or [])
        all_cards.append(card)
        save_deck(all_cards, deck_path)
        return card

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_tool_loop(
        self, system_prompt: str, messages: list, max_iterations: int = 10
    ) -> str:
        """
        Drive the Claude tool-use loop.

        Handles ``read_file``, ``write_file``, and ``get_due_cards`` tool calls
        automatically until Claude produces a final ``end_turn`` response.
        """
        tools = [read_file, write_file, get_due_cards_tool]
        _tool_map = {
            "read_file": read_file.__wrapped__ if hasattr(read_file, "__wrapped__") else read_file,
            "write_file": write_file.__wrapped__ if hasattr(write_file, "__wrapped__") else write_file,
            "get_due_cards": get_due_cards_tool.__wrapped__ if hasattr(get_due_cards_tool, "__wrapped__") else get_due_cards_tool,
        }

        # Use the beta tool runner which handles the loop automatically
        runner = self._client.beta.messages.tool_runner(
            model=self.MODEL,
            max_tokens=4096,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )

        last_text = ""
        for message in runner:
            for block in message.content:
                if hasattr(block, "type") and block.type == "text":
                    last_text = block.text

        return last_text

    def _evaluate_answer(self, question: str, correct_answer: str, user_answer: str) -> tuple[int, str]:
        """
        Ask Claude to judge a user's answer against the correct one.

        Returns
        -------
        Tuple of (quality_grade 0-5, feedback_string).
        """
        system_prompt = (
            "You are a strict but fair tutor evaluating flashcard answers. "
            "Compare the user's answer to the correct answer and respond with "
            "exactly one JSON object (no markdown) with two keys:\n"
            "  \"grade\": an integer 0-5 following SM-2 semantics "
            "(5=perfect, 4=good, 3=acceptable, 2=hard/wrong, 1=wrong, 0=blank/unrelated)\n"
            "  \"feedback\": a one-sentence explanation highlighting what was "
            "correct, missing, or wrong."
        )
        user_message = (
            f"Question: {question}\n"
            f"Correct answer: {correct_answer}\n"
            f"User answer: {user_answer or '(no answer provided)'}"
        )

        response = self._client.messages.create(
            model=self.MODEL,
            max_tokens=256,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        text = ""
        for block in response.content:
            if block.type == "text":
                text = block.text
                break

        try:
            data = json.loads(text)
            grade = int(data.get("grade", 3))
            feedback = str(data.get("feedback", ""))
        except (json.JSONDecodeError, KeyError, ValueError):
            # Fallback: crude keyword detection
            lower = text.lower()
            if any(w in lower for w in ["correct", "perfect", "excellent"]):
                grade = 4
            elif any(w in lower for w in ["incorrect", "wrong", "no"]):
                grade = 1
            else:
                grade = 3
            feedback = text[:200]

        return max(0, min(5, grade)), feedback

    @staticmethod
    def _parse_cards_json(text: str, skip_questions: set[str]) -> List[Card]:
        """
        Parse a JSON array of card dicts produced by Claude.

        Skips cards whose question is already in *skip_questions*.
        """
        # Strip markdown code fences if Claude added them anyway
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            # Remove first and last fence lines
            stripped = "\n".join(
                line for line in lines[1:] if not line.strip().startswith("```")
            ).strip()

        try:
            raw = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Claude did not return valid JSON for flashcards.\n"
                f"Raw response:\n{text[:500]}\nError: {exc}"
            ) from exc

        if not isinstance(raw, list):
            raise ValueError(f"Expected a JSON array, got: {type(raw).__name__}")

        cards: List[Card] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question", "")).strip()
            answer = str(item.get("answer", "")).strip()
            if not question or not answer:
                continue
            if question in skip_questions:
                continue
            tags = item.get("tags", [])
            if not isinstance(tags, list):
                tags = []
            cards.append(Card(question=question, answer=answer, tags=tags))

        return cards
