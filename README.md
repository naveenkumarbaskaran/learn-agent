# learn-agent-ai

An AI-powered adaptive learning agent that generates flashcards, runs spaced-repetition quizzes,
and tracks your performance -- all backed by Claude via the Anthropic SDK.

## Features

- **Study any topic or document** -- paste a topic string or point at a Markdown/text file;
  Claude generates 8-15 atomic flashcards automatically.
- **SM-2 spaced repetition** -- cards are scheduled using the proven SuperMemo-2 algorithm;
  easy cards appear less frequently, hard ones more often.
- **Claude-powered answer evaluation** -- Claude grades your answers and gives one-sentence
  feedback, removing the need for exact-match checking.
- **Persistent JSON decks** -- all cards and scheduling metadata are stored in a single
  human-readable JSON file that you can version-control.
- **Rich CLI** -- colourful terminal UI built with [Rich](https://github.com/Textualize/rich)
  and [Click](https://click.palletsprojects.com/).

## Installation

```bash
pip install learn-agent-ai
```

Or, from source:

```bash
git clone https://github.com/example/learn-agent-ai
cd learn-agent-ai
pip install -e .
```

## Quick Start

### 1. Set your Anthropic API key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### 2. Generate flashcards for a topic

```bash
# Plain topic
learn-agent study "the water cycle" --deck water.json

# From a Markdown file
learn-agent study notes/photosynthesis.md --deck photosynthesis.json
```

### 3. Take a quiz

```bash
learn-agent quiz --deck water.json
```

You will be shown each due card, type your answer, and Claude evaluates it instantly.

### 4. Add cards manually

```bash
learn-agent add "What is osmosis?" \
  "The movement of water through a semi-permeable membrane from low to high solute concentration" \
  --deck water.json --tags biology,cell
```

### 5. View deck statistics

```bash
learn-agent stats --deck water.json
```

## CLI Reference

```
Usage: learn-agent [OPTIONS] COMMAND [ARGS]...

  Learn Agent -- AI-powered adaptive learning with spaced repetition.

Commands:
  study   Generate flashcards for a topic or document file.
  quiz    Run an interactive quiz session for due cards.
  add     Manually add a flashcard to a deck.
  stats   Show statistics for a deck.
```

### `study`

```
learn-agent study TOPIC_OR_FILE [--deck PATH] [--api-key KEY]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--deck` | `deck.json` | Path to the JSON deck file |
| `--api-key` | `$ANTHROPIC_API_KEY` | Anthropic API key |

### `quiz`

```
learn-agent quiz [--deck PATH] [--max-cards N] [--api-key KEY]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--deck` | `deck.json` | Path to the JSON deck file |
| `--max-cards` | `20` | Maximum cards per session |
| `--api-key` | `$ANTHROPIC_API_KEY` | Anthropic API key |

### `add`

```
learn-agent add QUESTION ANSWER [--deck PATH] [--tags TAG1,TAG2]
```

### `stats`

```
learn-agent stats [--deck PATH]
```

## Deck Format

Decks are plain JSON files you can inspect and edit directly:

```json
{
  "topic": "the water cycle",
  "updated_at": "2024-01-15T10:30:00",
  "cards": [
    {
      "question": "What drives the water cycle?",
      "answer": "Solar energy and gravity",
      "easiness": 2.5,
      "interval": 6,
      "repetitions": 1,
      "due_date": "2024-01-21",
      "created_at": "2024-01-15T10:30:00",
      "last_reviewed": "2024-01-15T10:35:00",
      "tags": ["water-cycle", "energy"]
    }
  ]
}
```

## SM-2 Algorithm

The SM-2 algorithm schedules cards based on your performance:

| Grade | Meaning | Next interval |
|-------|---------|---------------|
| 5 | Perfect recall | `interval x easiness` |
| 4 | Good, slight hesitation | `interval x easiness` |
| 3 | Correct with difficulty | `interval x easiness` |
| 2 | Incorrect, easy to recall | Reset to 1 day |
| 1 | Incorrect | Reset to 1 day |
| 0 | Complete blackout | Reset to 1 day |

The easiness factor starts at 2.5 and adjusts after each review -- harder cards are reviewed sooner.

## Python API

```python
from learn_agent import LearnAgent

agent = LearnAgent()  # reads ANTHROPIC_API_KEY from env

# Generate cards
new_cards = agent.study("quantum entanglement", deck_path="quantum.json")
print(f"Generated {len(new_cards)} cards")

# Run a programmatic quiz
summary = agent.quiz(
    deck_path="quantum.json",
    max_cards=5,
    console_callback=lambda prompt: input(prompt),
)
print(summary)  # {"reviewed": 5, "correct": 4, "incorrect": 1}

# Add a card manually
agent.add_card(
    question="What is superposition?",
    answer="A quantum system existing in multiple states simultaneously until measured",
    deck_path="quantum.json",
    tags=["quantum", "state"],
)
```

## Requirements

- Python 3.10+
- [anthropic](https://pypi.org/project/anthropic/) >= 0.40.0
- [click](https://pypi.org/project/click/) >= 8.1
- [rich](https://pypi.org/project/rich/) >= 13.0
- An Anthropic API key

## License

MIT
