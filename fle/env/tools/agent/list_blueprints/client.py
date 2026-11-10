from typing import Any, Dict, List

from fle.env.tools import Tool
from fle.env.tools.construction import decode


class ListBlueprints(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)

    def __call__(self) -> List[Dict[str, Any]]:
        """
        Your saved blueprints.
        :return: One dict per blueprint: name, entity_count, entities (count by name), items, width, height
        """
        response, _ = self.execute(self.player_index)
        return decode(response, "list blueprints", self.get_error_message)["blueprints"]
