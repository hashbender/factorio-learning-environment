import re

from fle.env.entities import Position
from fle.env.game_types import Prototype
from fle.env.tools import Tool

_ERROR_PREFIX = re.compile(r'^\s*(?:\[string "[^"]*"\]:\d+:\s*)?')


class PlaceTile(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)

    def __call__(self, tile: Prototype, position: Position) -> Position:
        """
        Place one tile from a tile item (e.g. Prototype.Landfill on water, Prototype.StoneBrick,
        Prototype.Concrete) on the tile that contains the position. Uses one item.
        :param tile: Prototype of the tile item, e.g. Prototype.Landfill
        :param position: Position on the tile to build on (within build distance)
        :return: Position of the centre of the tile that was placed
        """
        if not isinstance(tile, Prototype):
            raise ValueError(
                "'place_tile' requires the Prototype of a tile item as the first argument, e.g. Prototype.Landfill"
            )
        if not isinstance(position, Position):
            raise ValueError("'place_tile' requires a Position as the second argument")
        name, _ = tile.value

        response, elapsed = self.execute(
            self.player_index, name, float(position.x), float(position.y)
        )

        if not isinstance(response, dict):
            message = _ERROR_PREFIX.sub("", str(response)).replace('"', "").strip()
            raise Exception(f"Could not place {name} - {message}")

        return Position(x=response["x"], y=response["y"])
