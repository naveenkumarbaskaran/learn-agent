"""SM-2 spaced repetition algorithm implementation."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional


@dataclass
class Card:
    """A single flashcard with SM-2 scheduling metadata."""

    question: str
    answer: str
    # SM-2 fields
    easiness: float = 2.5       # E-factor, minimum 1.3
    interval: int = 0            # days until next review
    repetitions: int = 0         # number of successful reviews
    due_date: str = field(default_factory=lambda: date.today().isoformat())
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_reviewed: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Card":
        return cls(**data)

    @property
    def is_due(self) -> bool:
        """Return True if this card is due for review today or earlier."""
        return date.fromisoformat(self.due_date) <= date.today()

    @property
    def days_until_due(self) -> int:
        delta = date.fromisoformat(self.due_date) - date.today()
        return delta.days


class SpacedRepetition:
    """
    SM-2 spaced repetition scheduler.

    Quality grades:
        0 – complete blackout
        1 – incorrect; correct answer remembered on seeing it
        2 – incorrect; easy to recall
        3 – correct; significant difficulty
        4 – correct; some hesitation
        5 – perfect recall
    """

    MIN_EASINESS = 1.3

    def review(self, card: Card, quality: int) -> Card:
        """
        Apply SM-2 algorithm to a card after a review session.

        Args:
            card: The card that was reviewed.
            quality: Response quality 0-5.

        Returns:
            Updated card with new scheduling metadata.
        """
        quality = max(0, min(5, quality))

        # Update easiness factor
        new_easiness = card.easiness + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        card.easiness = max(self.MIN_EASINESS, new_easiness)

        if quality < 3:
            # Incorrect: reset repetition count, review again soon
            card.repetitions = 0
            card.interval = 1
        else:
            # Correct
            if card.repetitions == 0:
                card.interval = 1
            elif card.repetitions == 1:
                card.interval = 6
            else:
                card.interval = math.ceil(card.interval * card.easiness)
            card.repetitions += 1

        card.due_date = (date.today() + timedelta(days=card.interval)).isoformat()
        card.last_reviewed = datetime.now().isoformat()
        return card

    def grade_from_text(self, response: str) -> int:
        """
        Convert a text correctness label to a quality grade.

        Expected values: 'perfect', 'good', 'okay', 'hard', 'wrong', 'blackout'
        Falls back to 3 (correct with difficulty) for unknown values.
        """
        mapping = {
            "perfect": 5,
            "easy": 5,
            "good": 4,
            "okay": 3,
            "ok": 3,
            "hard": 2,
            "difficult": 2,
            "wrong": 1,
            "incorrect": 1,
            "blackout": 0,
            "forgot": 0,
        }
        return mapping.get(response.strip().lower(), 3)


def load_deck(deck_path: str | Path) -> List[Card]:
    """Load a deck of cards from a JSON file. Returns empty list if file absent."""
    path = Path(deck_path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return [Card.from_dict(c) for c in data.get("cards", [])]


def save_deck(cards: List[Card], deck_path: str | Path, topic: str = "") -> None:
    """Persist a deck of cards to a JSON file."""
    path = Path(deck_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "topic": topic,
        "updated_at": datetime.now().isoformat(),
        "cards": [c.to_dict() for c in cards],
    }
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


def get_due_cards(deck_path: str | Path) -> List[Card]:
    """Return all cards from a deck that are due today or earlier."""
    cards = load_deck(deck_path)
    return [c for c in cards if c.is_due]
