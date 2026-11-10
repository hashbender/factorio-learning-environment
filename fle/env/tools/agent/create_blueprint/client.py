from typing import Any, Dict, List, Optional

from fle.env.entities import Entity
from fle.env.tools import Tool
from fle.env.tools.construction import Area, area_args, decode, entity_args


class CreateBlueprint(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)

    def __call__(
        self,
        name: str,
        area: Optional[Area] = None,
        entities: Optional[List[Entity]] = None,
    ) -> Dict[str, Any]:
        """
        Save your entities in an area (or a list of your entities) as a named blueprint.
        A blueprint with the same name is replaced. At most 20 blueprints of up to 500 entities.
        :param name: Blueprint name
        :param area: BoundingBox, or (left_top, right_bottom) Positions
        :param entities: Entities to include instead of an area
        :return: dict: name, entity_count, entities (count by name), items (to build it), width, height
        """
        wanted = entity_args(entities)
        if wanted is None and area is None:
            raise ValueError("create_blueprint needs an area or a list of entities")
        x1, y1, x2, y2 = area_args(area) if wanted is None else (None,) * 4
        response, _ = self.execute(self.player_index, str(name), x1, y1, x2, y2, wanted)
        return decode(response, "create blueprint", self.get_error_message)
