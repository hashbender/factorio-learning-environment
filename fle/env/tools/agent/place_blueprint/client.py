from typing import Any, Dict

from fle.env.entities import Direction, Position
from fle.env.tools import Tool
from fle.env.tools.construction import decode


class PlaceBlueprint(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)

    def __call__(
        self,
        name: str,
        position: Position,
        direction: Direction = Direction.UP,
        force_build: bool = False,
    ) -> Dict[str, Any]:
        """
        Place a saved blueprint as ghosts centred on a position. Construction robots build the ghosts.
        :param name: Blueprint name
        :param position: Centre of the placement
        :param direction: Direction.UP (as saved), RIGHT, DOWN or LEFT (turned)
        :param force_build: As shift-click: also place ghosts over trees and rocks, marking those for deconstruction
        :return: dict: placement_id, ghosts_placed, ghosts (count by name), items_needed, already_built,
            refused_count, refused (name, x, y, reason), obstacles_marked_for_deconstruction, center
        """
        if not isinstance(position, Position):
            x, y = self.get_position(position)
            position = Position(x=x, y=y)
        d = direction.value if isinstance(direction, Direction) else int(direction)
        response, _ = self.execute(
            self.player_index,
            str(name),
            float(position.x),
            float(position.y),
            d,
            bool(force_build),
        )
        return decode(response, "place blueprint", self.get_error_message)
