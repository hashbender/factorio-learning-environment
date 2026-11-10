"""Shared argument and reply handling for the blueprint and construction-robot tools."""

import json
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from fle.env.entities import BoundingBox, Entity, EntityGroup, Position

Area = Union[BoundingBox, Tuple[Position, Position]]

_GROUP_MEMBERS = ("belts", "pipes", "poles", "entities")


def area_args(area: Optional[Area]) -> Tuple[Any, Any, Any, Any]:
    """(x1, y1, x2, y2) of a BoundingBox or a (left_top, right_bottom) pair, or Nones."""
    if area is None:
        return None, None, None, None
    if isinstance(area, BoundingBox):
        a, b = area.left_top, area.right_bottom
    elif isinstance(area, (tuple, list)) and len(area) == 2:
        a, b = (
            p if isinstance(p, Position) else Position(x=p[0], y=p[1]) for p in area
        )
    else:
        raise ValueError(
            "area must be a BoundingBox or a (left_top, right_bottom) pair of Positions"
        )
    return float(a.x), float(a.y), float(b.x), float(b.y)


def entity_args(entities: Optional[Sequence[Any]]) -> Optional[List[Dict[str, Any]]]:
    """[{name, x, y}] for entities and entity groups (their members), or None."""
    if not entities:
        return None
    out = []
    for e in entities:
        if isinstance(e, EntityGroup):
            for attr in _GROUP_MEMBERS:
                for m in getattr(e, attr, None) or []:
                    out.append(
                        {
                            "name": m.name,
                            "x": float(m.position.x),
                            "y": float(m.position.y),
                        }
                    )
        elif isinstance(e, Entity) or (hasattr(e, "name") and hasattr(e, "position")):
            out.append(
                {"name": e.name, "x": float(e.position.x), "y": float(e.position.y)}
            )
        else:
            raise ValueError(f"Not an entity: {e!r}")
    return out


def _lists(value: Any, list_keys: Sequence[str]) -> Any:
    """table_to_json writes an empty Lua table as {}; read those as [] where a list is expected."""
    if isinstance(value, dict):
        return {
            k: ([] if k in list_keys and v in ({}, None) else _lists(v, list_keys))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_lists(v, list_keys) for v in value]
    return value


LIST_KEYS = (
    "blueprints",
    "entity_list",
    "refused",
    "not_marked",
    "not_cancelled",
    "networks",
    "ghosts_waiting",
    "deconstruction_waiting",
    "placements",
)


def decode(response: Any, what: str, error_message) -> Any:
    """The tool's hex-encoded JSON reply, or an exception with the game's message."""
    if isinstance(response, str):
        try:
            return _lists(
                json.loads(bytes.fromhex(response).decode("utf-8")), LIST_KEYS
            )
        except ValueError:
            pass
    raise Exception(f"Could not {what} - {error_message(str(response))}")
