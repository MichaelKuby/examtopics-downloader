# Anki Export Scripts

Python scripts that convert downloaded ExamTopics `.md` files into [Anki](https://apps.ankiweb.net/) flashcards.

## Quick Start

```bash
python3 scripts/exam-to-anki.py output.md
```

This produces `output-cleaned-anki.txt`, a tab-separated file ready to import into Anki.

## Importing into Anki

1. Open Anki and go to **File > Import**.
2. Select the generated `-anki.txt` file.
3. Set the separator to **Tab**.
4. Map the fields: Column 1 → Front, Column 2 → Back, Column 3 → Tags.
5. Click **Import**.

Cards are tagged by topic (e.g. `topic-1`, `topic-5`) so you can study by section.

## What Each Script Does

| Script | Purpose |
|---|---|
| `exam-to-anki.py` | One-command pipeline: clean then export. This is the one you run. |
| `clean-exam-topic.py` | Removes questions that have no answer. Saves `*-cleaned.md`. |
| `export-to-anki.py` | Converts a cleaned `.md` into an Anki-importable `.txt`. |

## Card Format

**Front:** Question text with answer choices (A, B, C, D, ...).

**Back:** Correct answer, top community comment (if available in the source file), and a link to the ExamTopics discussion thread.
