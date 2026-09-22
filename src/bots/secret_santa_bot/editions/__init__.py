"""Registry of every edition the bot knows about.

Adding a year:
    1. Copy ``edition_2026.py`` to ``edition_<year>.py`` and edit it.
    2. Import it below and add it to ``_ALL``.

Old editions stay registered forever — past games store their edition key and
are re-rendered through it.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from ..models import Edition
from .edition_2025 import EDITION as EDITION_2025
from .edition_2026 import EDITION as EDITION_2026

log = logging.getLogger(__name__)

_ALL: List[Edition] = [
    EDITION_2025,
    EDITION_2026,
]

EDITIONS: Dict[str, Edition] = {}
for _edition in _ALL:
    if _edition.key in EDITIONS:
        raise ValueError(f"duplicate edition key: {_edition.key}")
    EDITIONS[_edition.key] = _edition


def get_edition(key: str) -> Optional[Edition]:
    return EDITIONS.get(key)


def latest_edition() -> Edition:
    """The edition used when the host does not pick one.

    Prefers the edition whose year matches today, otherwise the newest one.
    """
    this_year = datetime.now().year
    for edition in _ALL:
        if edition.year == this_year:
            return edition
    return max(_ALL, key=lambda e: e.year)


def sorted_editions() -> List[Edition]:
    """Newest first — the order shown in the ``/secret-santa`` picker."""
    return sorted(_ALL, key=lambda e: e.year, reverse=True)


__all__ = ["EDITIONS", "get_edition", "latest_edition", "sorted_editions"]
