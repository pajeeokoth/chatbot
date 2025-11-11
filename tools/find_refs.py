"""
Scan the repository for deprecated keywords and print any occurrences with file and line numbers.
This helps confirm all LUIS references were removed from docs and notebooks.

Usage (from repo root):
  python tools/find_refs.py

By default, scans *.py, *.md, *.env, and *.ipynb (lightweight check for notebooks).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]

KEYWORDS = [
    "LUIS",
    "LuisRecognizer",
    "botbuilder-ai",
    "luis.ai",
]

TEXT_EXTS = {".py", ".md", ".env", ".txt", ".yml", ".yaml"}


def iter_files() -> Iterable[Path]:
    for p in ROOT.rglob("*"):
        if p.is_dir():
            # Skip common noise
            if p.name in {".git", "__pycache__", ".venv", "venv", "node_modules"}:
                continue
            # Don't descend into ignored dirs
            # (rglob still descends; we filter files below)
        else:
            # Exclude large/binary types
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".exe"}:
                continue
            yield p


def scan_text_file(path: Path):
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return
    for i, line in enumerate(text.splitlines(), start=1):
        for kw in KEYWORDS:
            if kw in line:
                print(f"{path.relative_to(ROOT)}:{i}: {line.strip()}")


def scan_notebook(path: Path):
    try:
        with path.open("r", encoding="utf-8") as f:
            nb = json.load(f)
    except Exception:
        return
    cells = nb.get("cells", [])
    for idx, cell in enumerate(cells, start=1):
        src = "".join(cell.get("source", []))
        for kw in KEYWORDS:
            if kw in src:
                print(f"{path.relative_to(ROOT)}:cell{idx}: contains '{kw}'")


def main():
    for path in iter_files():
        suf = path.suffix.lower()
        if suf in TEXT_EXTS:
            scan_text_file(path)
        elif suf == ".ipynb":
            scan_notebook(path)


if __name__ == "__main__":
    main()
