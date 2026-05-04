#!/usr/bin/env python3
import re
import sys
import os


ANSWER_RE = re.compile(r'^\*\*Answer:\s+\S.*\*\*', re.MULTILINE)
HEADING_SPLIT_RE = re.compile(r'(?=^## Exam )', re.MULTILINE)


def clean_file(filepath: str) -> None:
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    blocks = HEADING_SPLIT_RE.split(text)

    preamble = blocks[0] if blocks and not blocks[0].startswith("## Exam") else ""
    questions = blocks[1:] if preamble else blocks

    kept = [q for q in questions if ANSWER_RE.search(q)]
    removed = len(questions) - len(kept)

    base, ext = os.path.splitext(filepath)
    out_path = f"{base}-cleaned{ext}"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(preamble + "".join(kept))

    print(f"{filepath}: {len(questions)} questions found, {len(kept)} kept, {removed} removed")
    print(f"  -> {out_path}")


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <file.md> [file2.md ...]", file=sys.stderr)
        sys.exit(1)

    for path in sys.argv[1:]:
        clean_file(path)


if __name__ == "__main__":
    main()
