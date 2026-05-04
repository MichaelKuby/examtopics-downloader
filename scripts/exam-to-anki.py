#!/usr/bin/env python3
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CLEAN_SCRIPT = os.path.join(SCRIPT_DIR, "clean-exam-topic.py")
EXPORT_SCRIPT = os.path.join(SCRIPT_DIR, "export-to-anki.py")


def process_file(filepath: str) -> bool:
    print(f"\n{'=' * 60}")
    print(f"Processing: {filepath}")
    print(f"{'=' * 60}")

    result = subprocess.run([sys.executable, CLEAN_SCRIPT, filepath])
    if result.returncode != 0:
        print(f"ERROR: Cleaning failed for {filepath}", file=sys.stderr)
        return False

    base, ext = os.path.splitext(filepath)
    cleaned_path = f"{base}-cleaned{ext}"

    result = subprocess.run([sys.executable, EXPORT_SCRIPT, cleaned_path])
    if result.returncode != 0:
        print(f"ERROR: Anki export failed for {cleaned_path}", file=sys.stderr)
        return False

    os.remove(cleaned_path)
    return True


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <file.md> [file2.md ...]", file=sys.stderr)
        sys.exit(1)

    successes = 0
    for path in sys.argv[1:]:
        if process_file(path):
            successes += 1

    total = len(sys.argv) - 1
    if total > 1:
        print(f"\nDone: {successes}/{total} files processed successfully.")


if __name__ == "__main__":
    main()
