from typing import List, Optional

from fle.env.entities import BoundingBox, Position
from fle.env.tools import Tool


class GetCliffs(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)

    def __call__(
        self,
        position: Optional[Position] = None,
        radius: float = 40,
        limit: int = 25,
        area: Optional[BoundingBox] = None,
    ) -> List[Position]:
        """
        Get the positions of cliffs, nearest first.
        :param position: Position to measure from (default: the character's position)
        :param radius: Search radius around the position, in tiles (ignored when area is given)
        :param limit: Maximum number of cliffs returned
        :param area: Search inside this box instead of a radius
        :return: Cliff positions, nearest to the position first
        """
        x = y = None
        if position is not None:
            x, y = float(position.x), float(position.y)
        corners = [None, None, None, None]
        if area is not None:
            corners = [
                float(area.left_top.x),
                float(area.left_top.y),
                float(area.right_bottom.x),
                float(area.right_bottom.y),
            ]
        response, _ = self.execute(
            self.player_index, x, y, float(radius), int(limit), *corners
        )
        if not isinstance(response, dict):
            raise Exception(
                f"Could not get cliffs: {self.get_error_message(str(response))}"
            )
        cliffs = response.get("cliffs") or {}
        if isinstance(cliffs, dict):
            cliffs = [cliffs[k] for k in sorted(cliffs)]
        return [Position(x=c["x"], y=c["y"]) for c in cliffs]
