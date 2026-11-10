from typing import Any, Dict

from fle.env.tools import Tool
from fle.env.tools.construction import decode


class GetBlueprint(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)

    def __call__(self, name: str) -> Dict[str, Any]:
        """
        One saved blueprint, with its entities.
        :param name: Blueprint name
        :return: dict as list_blueprints, plus entity_list: name, x, y (relative to the centre), direction, recipe
        """
        response, _ = self.execute(self.player_index, str(name))
        return decode(response, "get blueprint", self.get_error_message)
