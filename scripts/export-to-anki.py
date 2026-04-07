#!/usr/bin/env python3
import html
import os
import re
import sys
from typing import Optional

HEADING_SPLIT_RE = re.compile(r"(?=^## Exam )", re.MULTILINE)
HEADING_RE = re.compile(r"^## Exam \S+ topic (\d+) question (\d+)")
ANSWER_RE = re.compile(r"^\*\*Answer:\s+(\S.*?)\*\*", re.MULTILINE)
LINK_RE = re.compile(r"\[View on ExamTopics\]\((https?://[^\)]+)\)")
COMMENT_RE = re.compile(
    r"^Comments:\s+(\S+)\s+Highly Voted\s+.+?\s+ago\s+"
    r"(?:Selected Answer:\s+\S+\s+)?"
    r"(.+?)\s+upvoted\s+(\d+)\s+times",
)
CHOICE_RE = re.compile(r"^[A-G]\.\s")


def parse_block(block: str) -> Optional[dict]:
    lines = block.split("\n")

    heading_m = HEADING_RE.match(lines[0])
    if not heading_m:
        return None
    topic, qnum = heading_m.group(1), heading_m.group(2)

    answer_m = ANSWER_RE.search(block)
    if not answer_m:
        return None
    answer = answer_m.group(1).strip()

    link_m = LINK_RE.search(block)
    link = link_m.group(1) if link_m else None

    marker_idx = None
    answer_line_idx = None
    all_q_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "[All AZ-204 Questions]":
            all_q_idx = i
        if stripped.startswith("Suggested Answer:"):
            marker_idx = i
        if stripped.startswith("**Answer:"):
            answer_line_idx = i
            break

    if all_q_idx is None or marker_idx is None or answer_line_idx is None:
        return None

    question_lines = [
        l.strip() for l in lines[all_q_idx + 1 : marker_idx] if l.strip()
    ]
    question_text = " ".join(question_lines)

    choices = []
    for line in lines[marker_idx + 1 : answer_line_idx]:
        if CHOICE_RE.match(line.strip()):
            choices.append(line.strip())

    comment = None
    for line in lines:
        comment_m = COMMENT_RE.match(line.strip())
        if comment_m:
            username = comment_m.group(1)
            text = comment_m.group(2).strip()
            votes = comment_m.group(3)
            comment = (username, text, votes)
            break

    return {
        "topic": topic,
        "qnum": qnum,
        "question": question_text,
        "choices": choices,
        "answer": answer,
        "link": link,
        "comment": comment,
    }


def build_front(card: dict) -> str:
    h = html.escape
    parts = [f'<b>Topic {card["topic"]} - Question {card["qnum"]}</b><br><br>']
    parts.append(h(card["question"]))
    if card["choices"]:
        parts.append("<br><br>")
        parts.append("<br>".join(h(c) for c in card["choices"]))
    return "".join(parts)


def build_back(card: dict) -> str:
    h = html.escape
    parts = [f'<b>{h(card["answer"])}</b>']
    if card["comment"]:
        username, text, votes = card["comment"]
        parts.append("<br><br>")
        parts.append(f"<i>{h(username)} ({h(votes)} upvotes):</i> {h(text)}")
    if card["link"]:
        parts.append("<br><br>")
        parts.append(
            f'<a href="{h(card["link"])}">View on ExamTopics</a>'
        )
    return "".join(parts)


def export_file(filepath: str) -> None:
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    blocks = HEADING_SPLIT_RE.split(text)

    cards = []
    skipped = 0
    for block in blocks:
        if not block.startswith("## Exam"):
            continue
        card = parse_block(block)
        if card is None:
            skipped += 1
            continue
        cards.append(card)

    base, ext = os.path.splitext(filepath)
    out_path = f"{base}-anki.txt"

    with open(out_path, "w", encoding="utf-8") as f:
        for card in cards:
            front = build_front(card)
            back = build_back(card)
            tag = f'topic-{card["topic"]}'
            front = front.replace("\t", " ")
            back = back.replace("\t", " ")
            f.write(f"{front}\t{back}\t{tag}\n")

    print(f"{filepath}: {len(cards)} cards exported, {skipped} blocks skipped")
    print(f"  -> {out_path}")


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <file.md> [file2.md ...]", file=sys.stderr)
        sys.exit(1)

    for path in sys.argv[1:]:
        export_file(path)


if __name__ == "__main__":
    main()
