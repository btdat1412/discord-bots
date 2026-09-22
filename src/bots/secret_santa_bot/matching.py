"""Pairing algorithms. Pure functions — no Discord, no database."""

import random
from typing import Dict, List

from .models import MatchStrategy


class MatchError(Exception):
    """Raised when the participant list cannot satisfy the strategy."""


def build_assignments(
    user_ids: List[str], strategy: MatchStrategy
) -> Dict[str, str]:
    """Return ``{giver_id: receiver_id}`` for every participant.

    Raises :class:`MatchError` when the list is unusable for the strategy.
    """
    if len(user_ids) < 2:
        raise MatchError("At least 2 participants are needed.")
    if len(set(user_ids)) != len(user_ids):
        raise MatchError("Duplicate participants in the list.")

    if strategy is MatchStrategy.CIRCLE:
        return _circle(user_ids)
    if strategy is MatchStrategy.PAIRS:
        return _pairs(user_ids)
    raise MatchError(f"Unknown match strategy: {strategy}")


def _circle(user_ids: List[str]) -> Dict[str, str]:
    """Shuffle into one cycle: each person gives to the next, last wraps round.

    A cycle over all participants is a derangement by construction, so nobody
    can draw themselves and no rescue swap is ever needed.
    """
    shuffled = list(user_ids)
    random.shuffle(shuffled)
    return {
        giver: shuffled[(i + 1) % len(shuffled)]
        for i, giver in enumerate(shuffled)
    }


def _pairs(user_ids: List[str]) -> Dict[str, str]:
    """Shuffle into mutual pairs: A gives to B and B gives to A."""
    if len(user_ids) % 2:
        raise MatchError(
            f"This edition swaps in pairs, so the number of participants must "
            f"be even. There are {len(user_ids)}."
        )
    shuffled = list(user_ids)
    random.shuffle(shuffled)
    assignments: Dict[str, str] = {}
    for a, b in zip(shuffled[0::2], shuffled[1::2]):
        assignments[a] = b
        assignments[b] = a
    return assignments


def santa_of(assignments: Dict[str, str]) -> Dict[str, str]:
    """Invert the mapping: ``{receiver_id: giver_id}``."""
    return {receiver: giver for giver, receiver in assignments.items()}
