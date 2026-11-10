"""The answer of connect_entities(..., dry_run=True).

A dry run builds nothing. It reports whether the game finds a route and every
placement along it passes the game's build check, what would be placed and
where, and what the character holds; or, when there is no route, the error the
real call would raise and the position it names.
"""

import re
from typing import Dict, List, Optional

from fle.env.entities import ConnectDryRun, Direction, PlannedEntity, Position

_BLOCKAGE = re.compile(
    r"cannot place [a-z0-9-]+ at \((-?\d+(?:\.\d+)?), (-?\d+(?:\.\d+)?)\)"
)
_DIRECTIONS = {0: Direction.UP, 4: Direction.RIGHT, 8: Direction.DOWN, 12: Direction.LEFT}
# Entities whose direction matters for what is built
_DIRECTED = ("belt", "pipe-to-ground", "underground")


def blocked_position(message: str) -> Optional[Position]:
    """The position a failure message names as blocked, if it names one."""
    match = _BLOCKAGE.search(message or "")
    if not match:
        return None
    return Position(x=float(match.group(1)), y=float(match.group(2)))


def planned_entities(planned: List[dict]) -> List[PlannedEntity]:
    """The action's plan as PlannedEntity objects (direction None where it has none)."""
    out = []
    for item in planned or []:
        name = str(item.get("name"))
        direction = None
        if any(part in name for part in _DIRECTED):
            try:
                direction = _DIRECTIONS.get(int(item.get("direction", 0)))
            except (TypeError, ValueError):
                direction = None
        out.append(
            PlannedEntity(
                name=name,
                position=Position(x=item["x"], y=item["y"]),
                direction=direction,
            )
        )
    return out


def success(
    entities: List[PlannedEntity],
    inventory: Dict[str, int],
    available: int,
    belt_changes: Optional[List[str]] = None,
) -> ConnectDryRun:
    required: Dict[str, int] = {}
    for e in entities:
        required[e.name] = required.get(e.name, 0) + 1
    held = {name: int(inventory.get(name, 0)) for name in required}
    missing = {
        name: count - held[name] for name, count in required.items() if count > held[name]
    }
    return ConnectDryRun(
        route_found=True,
        number_of_entities_required=len(entities),
        number_of_entities_available=available,
        required=required,
        in_inventory=held,
        missing=missing,
        enough_in_inventory=not missing,
        entities=entities,
        belt_changes=list(belt_changes or []),
    )


def failure(message: str, available: int = 0) -> ConnectDryRun:
    return ConnectDryRun(
        route_found=False,
        number_of_entities_available=available,
        error=message,
        blocked_at=blocked_position(message),
    )
