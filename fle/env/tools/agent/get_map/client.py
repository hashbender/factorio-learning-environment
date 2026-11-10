from typing import Any, Optional

from fle.env.entities import Position
from fle.env.tools import Tool

MAX_RADIUS = 32


def _as_list(value: Any) -> list:
    """Lua sequences can arrive as lists or as {1: ..., 2: ...} dicts."""
    if isinstance(value, dict):
        return [value[k] for k in sorted(value, key=lambda k: int(k))]
    return list(value or [])


class MapText(str):
    """The map text. print() logs values with repr(), which would show a plain
    string's newlines as \\n; this one prints as the grid itself."""

    def __repr__(self) -> str:
        return str.__str__(self)


class GetMap(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)

    def __call__(self, position: Optional[Position] = None, radius: int = 15) -> str:
        """
        Get a text map of the area around a position: one character per tile, with a legend.
        Shows what is on each tile (entities by name, belts with their direction,
        resources, water, cliffs, trees, rocks and you). It shows facts only.
        :param position: Centre of the map (default: your position)
        :param radius: Tiles from the centre to each edge, 1 to 32 (default 15)
        :example print(get_map(Position(x=0, y=0), radius=10))
        :return: The map as text: a header with the covered x and y range, one row per y, then the legend
        """
        if position is not None and not isinstance(position, Position):
            raise ValueError("The position argument must be a Position or None")
        radius = int(radius)
        if radius < 1 or radius > MAX_RADIUS:
            raise ValueError(f"radius must be 1 to {MAX_RADIUS} tiles, got {radius}")
        x = position.x if position is not None else None
        y = position.y if position is not None else None

        response, _ = self.execute(self.player_index, x, y, radius)
        if not isinstance(response, dict) or "rows" not in response:
            raise Exception(
                f"Could not get map: {self.get_error_message(str(response))}"
            )

        x0, x1 = int(response["x0"]), int(response["x1"])
        y0, y1 = int(response["y0"]), int(response["y1"])
        rows = [str(r) for r in _as_list(response["rows"])]
        width = max(len(str(y0)), len(str(y1)))
        lines = [
            f"Map x {x0}..{x1} (left to right), y {y0}..{y1} (top to bottom),"
            f" one character per tile; each row starts with its y"
        ]
        for i, row in enumerate(rows):
            lines.append(f"{str(y0 + i).rjust(width)} {row}")
        lines.append("Legend:")
        for item in _as_list(response.get("legend")):
            lines.append(f"  {item['symbol']} {item['text']}")
        return MapText("\n".join(lines))
