"""Parsing helpers for bulk card input and CSV import/export."""

from __future__ import annotations

import csv
import io
import re

ARTICLES = ("der", "die", "das")
# Order matters: the most explicit separators win.
_SPACED_DASH = re.compile(r"\s+[-–—]\s+")


def split_line(line: str) -> tuple[str, str] | None:
    """Split one "word - translation" line. Supports tab, " - ", ":", "-" separators."""
    line = line.strip()
    if not line:
        return None
    if "\t" in line:
        left, right = line.split("\t", 1)
    elif _SPACED_DASH.search(line):
        left, right = _SPACED_DASH.split(line, maxsplit=1)
    elif ":" in line:
        left, right = line.split(":", 1)
    elif "-" in line or "–" in line or "—" in line:
        left, right = re.split(r"[-–—]", line, maxsplit=1)
    else:
        return None
    left, right = left.strip(), right.strip()
    if not left or not right:
        return None
    return left, right


def detect_article(term: str) -> tuple[str, str]:
    """'der Hund' -> ('der', 'Hund'). Returns ('', term) when no article prefix."""
    parts = term.split(maxsplit=1)
    if len(parts) == 2 and parts[0].lower() in ARTICLES:
        return parts[0].lower(), parts[1]
    return "", term


def parse_bulk(text: str, track: str = "en") -> tuple[list[dict], list[int]]:
    """Parse pasted text. Returns (cards, bad_line_numbers) — line numbers are 1-based."""
    cards: list[dict] = []
    bad: list[int] = []
    for i, raw in enumerate((text or "").splitlines(), start=1):
        if not raw.strip():
            continue
        pair = split_line(raw)
        if not pair:
            bad.append(i)
            continue
        term, translation = pair
        article = ""
        if track == "de":
            article, _ = detect_article(term)
        cards.append({"term": term, "translation": translation, "article": article})
    return cards, bad


CSV_FIELDS = ["term", "translation", "definition", "example", "article"]


def cards_to_csv(cards) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_FIELDS)
    for c in cards:
        w.writerow([getattr(c, f) if not isinstance(c, dict) else c.get(f, "") for f in CSV_FIELDS])
    return buf.getvalue()


def csv_to_cards(content: str) -> list[dict]:
    content = content.lstrip("﻿")
    sample = content[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(content), dialect))
    if not rows:
        return []
    header = [h.strip().lower() for h in rows[0]]
    if "term" in header:
        idx = {f: header.index(f) for f in CSV_FIELDS if f in header}
        body = rows[1:]
    else:  # headerless: term, translation, ...
        idx = {f: i for i, f in enumerate(CSV_FIELDS)}
        body = rows
    out = []
    for r in body:

        def get(f, r=r):
            i = idx.get(f)
            return r[i].strip() if i is not None and i < len(r) else ""

        if get("term") and get("translation"):
            out.append({f: get(f) for f in CSV_FIELDS})
    return out
