from typing import Any, Dict

from fle.env.tools import Tool
from fle.env.tools.construction import decode


class GetConstructionStatus(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)

    def __call__(self) -> Dict[str, Any]:
        """
        Roboport networks, ghosts and deconstruction orders of your force, and what stops the robots.
        :return: dict: networks (id, roboports, roboports_no_power, roboports_low_power, construction_robots,
            construction_robots_idle, logistic_robots, logistic_robots_idle, storage), ghosts, ghosts_waiting
            (reason, count, x, y), deconstruction, deconstruction_waiting, placements (id, blueprint, x, y,
            ghosts_placed, ghosts_waiting, built)
        """
        response, _ = self.execute(self.player_index)
        return decode(response, "get construction status", self.get_error_message)
