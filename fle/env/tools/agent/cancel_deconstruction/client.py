from typing import Any, Dict, List, Optional

from fle.env.entities import Entity
from fle.env.tools import Tool
from fle.env.tools.construction import Area, area_args, decode, entity_args


class CancelDeconstruction(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)

    def __call__(
        self, area: Optional[Area] = None, entities: Optional[List[Entity]] = None
    ) -> Dict[str, Any]:
        """
        Cancel deconstruction orders in an area, or of listed entities.
        :param area: BoundingBox, or (left_top, right_bottom) Positions
        :param entities: Entities instead of an area
        :return: dict: cancelled, cancelled_by_name, not_cancelled (name, x, y, reason)
        """
        wanted = entity_args(entities)
        if wanted is None and area is None:
            raise ValueError(
                "cancel_deconstruction needs an area or a list of entities"
            )
        x1, y1, x2, y2 = area_args(area) if wanted is None else (None,) * 4
        response, _ = self.execute(self.player_index, x1, y1, x2, y2, wanted)
        return decode(response, "cancel deconstruction", self.get_error_message)
