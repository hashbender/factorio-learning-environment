import re
from typing import List

from fle.env.entities import Position
from fle.env.tools import Tool

_ERROR_PREFIX = re.compile(r'^\s*(?:\[string "[^"]*"\]:\d+:\s*)?')


class ThrowCliffExplosives(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)

    def __call__(self, position: Position) -> List[Position]:
        """
        Throw one cliff-explosives at a position within throw range. Every cliff within the
        explosion's radius of the position is destroyed. The item is used even if no cliff is hit.
        :param position: Position to throw at
        :return: Positions of the cliffs destroyed (empty if none)
        """
        if not isinstance(position, Position):
            raise ValueError("'throw_cliff_explosives' requires a Position")

        response, elapsed = self.execute(
            self.player_index, float(position.x), float(position.y)
        )

        if not isinstance(response, dict):
            message = _ERROR_PREFIX.sub("", str(response)).replace('"', "").strip()
            raise Exception(f"Could not throw cliff-explosives - {message}")

        cliffs = response.get("cliffs") or []
        if isinstance(cliffs, dict):  # an empty or integer-keyed Lua table
            cliffs = [cliffs[k] for k in sorted(cliffs, key=lambda k: int(k))]
        return [Position(x=c["x"], y=c["y"]) for c in cliffs]
