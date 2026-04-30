"""Wikilink parser and renderer."""

import re

# Match [[target|display]] or [[target]]
WIKILINK_PATTERN = re.compile(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]')


def extract_wikilinks(text: str) -> list[dict]:
    """Extract all wikilinks from text."""
    links = []
    for match in WIKILINK_PATTERN.finditer(text):
        links.append({
            "target": match.group(1).strip(),
            "display": match.group(2).strip() if match.group(2) else match.group(1).strip(),
        })
    return links


def has_wikilink(text: str, target: str) -> bool:
    """Check if text already contains a wikilink to target."""
    for match in WIKILINK_PATTERN.finditer(text):
        if match.group(1).strip() == target:
            return True
    return False
