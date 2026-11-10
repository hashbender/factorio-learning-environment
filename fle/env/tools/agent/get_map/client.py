from typing import Any, List, Optional

from fle.env.entities import Position
from fle.env.tools import Tool

MAX_SIDE = 64
MAX_RADIUS = 31

# The server sends inserters as the side they drop on; they print as arrows
INSERTER_ARROWS = {"n": "↑", "e": "→", "s": "↓", "w": "←"}
_INSERTER_TABLE = str.maketrans(INSERTER_ARROWS)


def _as_list(value: Any) -> list:
    """Lua sequences can arrive as lists or as {1: ..., 2: ...} dicts."""
    if isinstance(value, dict):
        return [value[k] for k in sorted(value, key=lambda k: int(k))]
    return list(value or [])


def column_header(x0: int, x1: int) -> List[str]:
    """The x of every column, written top to bottom above it: a sign row when
    any x is negative, then one row per digit."""
    xs = range(x0, x1 + 1)
    digits = max(len(str(abs(x))) for x in xs)
    lines = []
    if x0 < 0:
        lines.append("".join("-" if x < 0 else " " for x in xs))
    for d in range(digits):
        lines.append("".join(str(abs(x)).rjust(digits)[d] for x in xs))
    return lines


def render_map(response: dict) -> str:
    x0, x1 = int(response["x0"]), int(response["x1"])
    y0, y1 = int(response["y0"]), int(response["y1"])
    rows = [str(r).translate(_INSERTER_TABLE) for r in _as_list(response["rows"])]
    width = max(len(str(y0)), len(str(y1)))
    lines = [
        f"Map x {x0}..{x1}, y {y0}..{y1} ({x1 - x0 + 1} x {y1 - y0 + 1} tiles), one character per tile."
        f" The x of a column is written above it, top to bottom; each row starts with its y."
        f" x grows to the right, y grows downward."
        f" Tile x, y covers x to x+1 and y to y+1; its centre is Position(x + 0.5, y + 0.5)."
    ]
    if "player_x" in response and "player_y" in response:
        lines.append(
            f"You are on tile x={int(response['player_x'])}, y={int(response['player_y'])}."
        )
    pad = " " * (width + 1)
    lines.extend(pad + line for line in column_header(x0, x1))
    for i, row in enumerate(rows):
        lines.append(f"{str(y0 + i).rjust(width)} {row}")
    lines.append("Legend:")
    for item in _as_list(response.get("legend")):
        symbol = str(item["symbol"])
        if symbol == "INSERTER":
            symbol = " ".join(INSERTER_ARROWS[k] for k in "nesw")
        lines.append(f"  {symbol} {item['text']}")
    return "\n".join(lines)


class MapText(str):
    """The map text. print() logs values with repr(), which would show a plain
    string's newlines as \\n; this one prints as the grid itself."""

    def __repr__(self) -> str:
        return str.__str__(self)


class GetMap(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)

    def __call__(
        self,
        position: Optional[Position] = None,
        radius: int = 15,
        left_top: Optional[Position] = None,
        right_bottom: Optional[Position] = None,
    ) -> str:
        """
        Get a text map of an area: one character per tile, with x and y on the axes and a legend.
        Shows what is on each tile: entity footprints by name, belts and inserters with their
        direction, pipes, electric poles, resources by type, water, cliffs, trees, rocks and you.
        It reads the map only: it builds nothing, takes no game time and works at any distance.
        Tiles the map has not charted show as ?. It shows facts only.
        The area is either position and radius, or the box between left_top and right_bottom.
        The most one call returns is 64 x 64 tiles.
        :param position: Centre of the map (default: your position)
        :param radius: Tiles from the centre to each edge, 1 to 31 (default 15, a 31 x 31 map)
        :param left_top: One corner of a box, instead of position and radius
        :param right_bottom: The opposite corner of the box; both corner tiles are included
        :example print(get_map(Position(x=0, y=0), radius=10))
        :example print(get_map(left_top=Position(x=-20, y=5), right_bottom=Position(x=10, y=25)))
        :return: The map as text: a header, the x of each column, one row per y, then the legend
        """
        for name, value in (
            ("position", position),
            ("left_top", left_top),
            ("right_bottom", right_bottom),
        ):
            if value is not None and not isinstance(value, Position):
                raise ValueError(f"The {name} argument must be a Position or None")

        if (left_top is None) != (right_bottom is None):
            raise ValueError("left_top and right_bottom must be given together")
        if left_top is not None:
            if position is not None:
                raise ValueError(
                    "Give either position and radius, or left_top and right_bottom, not both"
                )
            xs = sorted((int(left_top.x // 1), int(right_bottom.x // 1)))
            ys = sorted((int(left_top.y // 1), int(right_bottom.y // 1)))
            width, height = xs[1] - xs[0] + 1, ys[1] - ys[0] + 1
            if width > MAX_SIDE or height > MAX_SIDE:
                raise ValueError(
                    f"The map area is {width} x {height} tiles; the most one call returns is "
                    f"{MAX_SIDE} x {MAX_SIDE} tiles"
                )
            args = (xs[0], ys[0], xs[1], ys[1], None)
        else:
            radius = int(radius)
            if radius < 1 or radius > MAX_RADIUS:
                raise ValueError(
                    f"radius must be 1 to {MAX_RADIUS} tiles, got {radius}; the most one call "
                    f"returns is {MAX_SIDE} x {MAX_SIDE} tiles"
                )
            if position is not None:
                cx, cy = int(position.x // 1), int(position.y // 1)
                args = (cx - radius, cy - radius, cx + radius, cy + radius, None)
            else:
                args = (None, None, None, None, radius)

        response, _ = self.execute(self.player_index, *args)
        if not isinstance(response, dict) or "rows" not in response:
            raise Exception(
                f"Could not get map: {self.get_error_message(str(response))}"
            )
        return MapText(render_map(response))
