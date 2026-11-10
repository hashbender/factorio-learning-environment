"""The answer of connect_entities(..., dry_run=True).

A dry run builds nothing. It reports whether the game finds a route and every
placement along it passes the game's build check, what would be placed and
where, and what the character holds; or, when there is no route, the error the
real call would raise and the position it names.
"""

import re
from typing import Dict, List, Optional

from fle.env.entities import Direction, Position

_BLOCKAGE = re.compile(
    r"cannot place [a-z0-9-]+ at \((-?\d+(?:\.\d+)?), (-?\d+(?:\.\d+)?)\)"
)
_DIRECTIONS = {0: Direction.UP, 4: Direction.RIGHT, 8: Direction.DOWN, 12: Direction.LEFT}
# Entities whose direction matters for what is built
_DIRECTED = ("belt", "pipe-to-ground", "underground")
REPR_POSITIONS = 40


def blocked_position(message: str) -> Optional[Position]:
    """The position a failure message names as blocked, if it names one."""
    match = _BLOCKAGE.search(message or "")
    if not match:
        return None
    return Position(x=float(match.group(1)), y=float(match.group(2)))


def planned_entities(planned: List[dict]) -> List[dict]:
    """The action's plan as [{name, position, direction}] (direction None where it has none)."""
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
            {
                "name": name,
                "position": Position(x=item["x"], y=item["y"]),
                "direction": direction,
            }
        )
    return out


class ConnectDryRun(dict):
    """A dict that prints as one readable line."""

    def __repr__(self) -> str:
        if not self.get("route_found"):
            at = self.get("blocked_at")
            where = f", blocked_at=({at.x}, {at.y})" if at is not None else ""
            return f"ConnectDryRun(route_found=False{where}, error={self.get('error')!r})"
        parts = [
            "route_found=True",
            f"required={self.get('required')}",
            f"in_inventory={self.get('in_inventory')}",
            f"missing={self.get('missing')}",
        ]
        if self.get("belt_changes"):
            parts.append(f"belt_changes={self.get('belt_changes')}")
        entities = self.get("entities") or []
        shown = []
        for e in entities[:REPR_POSITIONS]:
            p = e["position"]
            facing = f" {e['direction'].name}" if e.get("direction") is not None else ""
            shown.append(f"{e['name']} at ({p.x}, {p.y}){facing}")
        more = len(entities) - len(shown)
        if more > 0:
            shown.append(f"... and {more} more in ['entities']")
        parts.append(f"entities=[{', '.join(shown)}]")
        return f"ConnectDryRun({', '.join(parts)})"

    __str__ = __repr__


def success(
    entities: List[dict],
    inventory: Dict[str, int],
    available: int,
    belt_changes: Optional[List[str]] = None,
) -> ConnectDryRun:
    required: Dict[str, int] = {}
    for e in entities:
        required[e["name"]] = required.get(e["name"], 0) + 1
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
        error=None,
        blocked_at=None,
    )


def failure(message: str, available: int = 0) -> ConnectDryRun:
    return ConnectDryRun(
        route_found=False,
        number_of_entities_required=None,
        number_of_entities_available=available,
        required={},
        in_inventory={},
        missing={},
        enough_in_inventory=False,
        entities=[],
        belt_changes=[],
        error=message,
        blocked_at=blocked_position(message),
    )
