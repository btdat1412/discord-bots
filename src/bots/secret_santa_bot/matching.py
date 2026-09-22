"""Pairing algorithms. Pure functions — no Discord, no database."""

import random
from typing import Dict, List, Optional, Sequence, Set

from .models import MatchStrategy

MATCH_ATTEMPTS = 500


class MatchError(Exception):
    """Raised when the participant list cannot satisfy the strategy."""


Blocked = Dict[str, Set[str]]

def block_across(
    sides: Sequence[Sequence[str]], blocked: Optional[Blocked] = None
) -> Blocked:
    result: Blocked = blocked if blocked is not None else {}
    for index, side in enumerate(sides):
        others = [
            member
            for other_index, other in enumerate(sides)
            if other_index != index
            for member in other
        ]
        if not others:
            continue
        for giver in side:
            result.setdefault(giver, set()).update(others)
    return result


def _violates(assignments: Dict[str, str], blocked: Blocked) -> bool:
    return any(
        receiver in blocked.get(giver, ()) for giver, receiver in assignments.items()
    )


def build_assignments(
    user_ids: Sequence[str],
    strategy: MatchStrategy,
    blocked: Optional[Blocked] = None,
) -> Dict[str, str]:
    """Return ``{giver_id: receiver_id}`` for every participant.

    ``blocked`` names pairs that must never be matched — see
    :func:`block_across`. Raises :class:`MatchError` when the list is unusable,
    or when no arrangement respects the exclusions.
    """
    user_ids = list(user_ids)
    if len(user_ids) < 2:
        raise MatchError("Cần ít nhất 2 người.")
    if len(set(user_ids)) != len(user_ids):
        raise MatchError("Danh sách có người bị trùng.")
    if strategy is not MatchStrategy.CIRCLE:
        raise MatchError(f"Không biết kiểu ghép: {strategy}")

    blocked = blocked or {}
    for _ in range(MATCH_ATTEMPTS):
        assignments = _circle(user_ids)
        if not _violates(assignments, blocked):
            return assignments

    # Deliberately says nothing about how the draw is made — the message
    # reaches the channel, and players have no business learning that the bot
    # reshuffles, let alone how often.
    raise MatchError(
        "Không xếp được vòng nào hợp lệ với danh sách hiện tại. "
        "Rủ thêm người rồi thử lại."
    )


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


def santa_of(assignments: Dict[str, str]) -> Dict[str, str]:
    """Invert the mapping: ``{receiver_id: giver_id}``."""
    return {receiver: giver for giver, receiver in assignments.items()}
