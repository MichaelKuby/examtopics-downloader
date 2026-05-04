#!/usr/bin/env python3
import hashlib
import html
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Optional
from urllib.parse import urlparse

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
SUGGESTED_RE = re.compile(r"^Suggested Answer:\s*(.+?)\s*$")
ALL_QUESTIONS_RE = re.compile(r"^\[All .+ Questions\]$")
BOILERPLATE_NOTE_RE = re.compile(
    r"Note:\s+The question is included in a number of questions that depicts the "
    r"identical set-up\.\s+However,\s+every question has a distinctive result\.\s+"
    r"Establish if the solution satisfies the requirements\.\s*",
    re.IGNORECASE,
)
SERIES_NOTE_RE = re.compile(
    r"Note:\s+This question is part of a series of questions that present the same scenario\.\s+"
    r"Each question in the series contains a unique solution that might meet the stated goals\.\s+"
    r"Some questions?\s+sets might have more than one correct solution,\s+while others might not have a correct solution\.\s*"
    r"After you answer a question in this section,\s+you will NOT be able to return to it\.\s+"
    r"As a result,\s+these questions will not appear in the review screen\.\s*",
    re.IGNORECASE,
)
IMAGE_RE = re.compile(r"^!\[(?P<alt>[^\]]*)\]\((?P<url>https?://[^)\s]+)\)\s*$")
DEFAULT_IMAGE_EXT = ".png"
USER_AGENT = "examtopics-downloader/1.0 (+https://github.com/thatonecodes/examtopics-downloader)"
IMAGE_MAX_RETRIES = 5
IMAGE_INITIAL_BACKOFF_SEC = 1.0
IMAGE_BACKOFF_FACTOR = 2.0
IMAGE_JITTER_MAX_SEC = 0.25
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}


def normalize_question_text(text: str) -> str:
    """Normalize question text readability while preserving meaning."""
    text = BOILERPLATE_NOTE_RE.sub("", text)
    text = SERIES_NOTE_RE.sub("", text)
    # Ensure period-delimited sentences don't get glued together (e.g. "domain.You").
    text = re.sub(r"\.(?=[A-Za-z0-9])", ". ", text)
    # Put solution scenarios on a dedicated line.
    text = re.sub(r"\s*Solution:\s*", "\n\nSolution: ", text)
    # Collapse excessive spaces while preserving newlines for display formatting.
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def split_text_and_images(lines: list[str], expect_alt: str) -> tuple[list[str], list[str]]:
    """Walk a slice of markdown lines and split out image URLs whose alt matches.

    Lines whose entire content is `![alt](url)` are routed to the URL list.
    All other non-empty lines (after stripping any inline image markdown) are
    returned as text lines for further joining.
    """
    text_lines: list[str] = []
    image_urls: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        m = IMAGE_RE.match(line)
        if m and m.group("alt") == expect_alt:
            image_urls.append(m.group("url"))
            continue
        text_lines.append(line)
    return text_lines, image_urls


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

    answer_line_idx = None
    all_q_idx = None
    suggested_answer = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if ALL_QUESTIONS_RE.match(stripped):
            all_q_idx = i
        if stripped.startswith("Suggested Answer:"):
            sa_m = SUGGESTED_RE.match(stripped)
            if sa_m:
                raw = sa_m.group(1).strip()
                clean = raw.replace("\U0001f5f3\ufe0f", "").strip()
                if clean:
                    suggested_answer = clean
        if stripped.startswith("**Answer:"):
            answer_line_idx = i
            break

    if all_q_idx is None or answer_line_idx is None:
        return None

    question_text_lines = []
    question_image_urls = []
    choices = []
    for raw in lines[all_q_idx + 1 : answer_line_idx]:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("Suggested Answer:"):
            continue
        image_m = IMAGE_RE.match(line)
        if image_m and image_m.group("alt") == "":
            question_image_urls.append(image_m.group("url"))
            continue
        if CHOICE_RE.match(line):
            choices.append(line)
            continue
        question_text_lines.append(line)

    question_text = normalize_question_text(" ".join(question_text_lines))

    _, answer_image_urls = split_text_and_images(
        lines[answer_line_idx + 1 :], expect_alt="answer"
    )

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
        "question_images": question_image_urls,
        "answer_images": answer_image_urls,
        "choices": choices,
        "suggested_answer": suggested_answer,
        "answer": answer,
        "link": link,
        "comment": comment,
    }


def image_filename_for(url: str) -> str:
    """Produce a stable, content-addressed filename for a given image URL.

    Same URL -> same filename across runs, so re-imports don't duplicate
    media in Anki's collection.media folder.
    """
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    if not ext or len(ext) > 5:
        ext = DEFAULT_IMAGE_EXT
    return f"examtopics_{digest}{ext}"


def download_image(url: str, media_dir: str) -> Optional[str]:
    """Download `url` into `media_dir` (idempotent) and return the local filename.

    Returns None on failure; failures are logged to stderr and don't abort the run.
    """
    filename = image_filename_for(url)
    target = os.path.join(media_dir, filename)
    if os.path.exists(target):
        return filename
    for attempt in range(IMAGE_MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp, open(target, "wb") as out:
                out.write(resp.read())
            return filename
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as e:
            retryable = True
            if isinstance(e, urllib.error.HTTPError):
                retryable = e.code in RETRYABLE_HTTP_CODES
            if attempt >= IMAGE_MAX_RETRIES or not retryable:
                print(f"  ! failed to download {url}: {e}", file=sys.stderr)
                if os.path.exists(target):
                    try:
                        os.remove(target)
                    except OSError:
                        pass
                return None

            delay = (IMAGE_INITIAL_BACKOFF_SEC * (IMAGE_BACKOFF_FACTOR ** attempt)) + random.uniform(0, IMAGE_JITTER_MAX_SEC)
            print(
                f"  ! retrying image download ({attempt + 1}/{IMAGE_MAX_RETRIES}) in {delay:.2f}s: {url} ({e})",
                file=sys.stderr,
            )
            time.sleep(delay)

    return None


def materialize_images(card: dict, media_dir: str, cache: dict[str, Optional[str]]) -> None:
    """Resolve every image URL on the card to a local filename in `media_dir`.

    Mutates the card to add `question_image_files` and `answer_image_files`,
    each a list of local filenames (skipping any URL that failed to download).
    `cache` is shared across cards so each unique URL is only fetched once.
    """
    for src_key, dst_key in (
        ("question_images", "question_image_files"),
        ("answer_images", "answer_image_files"),
    ):
        files: list[str] = []
        for url in card.get(src_key, []):
            if url in cache:
                fname = cache[url]
            else:
                fname = download_image(url, media_dir)
                cache[url] = fname
            if fname:
                files.append(fname)
        card[dst_key] = files


def build_front(card: dict) -> str:
    h = html.escape
    parts = [f'<b>Topic {card["topic"]} - Question {card["qnum"]}</b><br><br>']
    parts.append(h(card["question"]).replace("\n", "<br>"))
    if card.get("question_image_files"):
        parts.append("<br><br>")
        parts.append(
            "<br>".join(f'<img src="{h(f)}">' for f in card["question_image_files"])
        )
    if card["choices"]:
        parts.append("<br><br>")
        parts.append("<br>".join(h(c) for c in card["choices"]))
    return "".join(parts)


def build_back(card: dict) -> str:
    h = html.escape
    parts = [f'<b>Answer: {h(card["answer"])}</b>']
    if card.get("answer_image_files"):
        parts.append("<br><br>")
        parts.append(
            "<br>".join(f'<img src="{h(f)}">' for f in card["answer_image_files"])
        )
    if card["suggested_answer"]:
        parts.append(f'<br><br><b>Suggested Answer: {h(card["suggested_answer"])}</b>')
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

    base, _ext = os.path.splitext(filepath)
    out_path = f"{base}-anki.txt"
    media_dir = f"{base}-anki-media"

    has_images = any(c.get("question_images") or c.get("answer_images") for c in cards)
    if has_images:
        os.makedirs(media_dir, exist_ok=True)

    download_cache: dict[str, Optional[str]] = {}
    for card in cards:
        materialize_images(card, media_dir, download_cache)

    with open(out_path, "w", encoding="utf-8") as f:
        for card in cards:
            front = build_front(card)
            back = build_back(card)
            tag = f'topic-{card["topic"]}'
            front = front.replace("\t", " ")
            back = back.replace("\t", " ")
            f.write(f"{front}\t{back}\t{tag}\n")

    downloaded = sum(1 for v in download_cache.values() if v)
    failed = sum(1 for v in download_cache.values() if v is None)

    print(f"{filepath}: {len(cards)} cards exported, {skipped} blocks skipped")
    print(f"  -> {out_path}")
    if has_images:
        print(f"  -> {media_dir}/ ({downloaded} images, {failed} failed)")


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <file.md> [file2.md ...]", file=sys.stderr)
        sys.exit(1)

    for path in sys.argv[1:]:
        export_file(path)


if __name__ == "__main__":
    main()
