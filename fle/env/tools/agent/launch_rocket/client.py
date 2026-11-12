from typing import Union, cast

from fle.env.entities import Position, RocketSilo
from fle.env.game_types import Prototype
from fle.env.tools.agent.get_entity.client import GetEntity
from fle.env.tools import Tool


class LaunchRocket(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)
        self.get_entity = GetEntity(connection, game_state)

    def __call__(self, silo: Union[Position, RocketSilo]) -> RocketSilo:
        """
        Launch a rocket.
        :param silo: Rocket silo
        :return: The updated RocketSilo
        """

        if isinstance(silo, Position):
            position = silo
        else:
            position = silo.position

        response, _ = self.execute(self.player_index, position.x, position.y)
        if isinstance(response, str) or not isinstance(response, dict) or not response.get("launched"):
            msg = response if isinstance(response, str) else "no answer from the game"
            raise Exception(f"Cannot launch rocket. {self.get_error_message(msg)}")
        try:
            silo_position = Position(x=response["x"], y=response["y"])
        except Exception:
            silo_position = position
        return cast(
            Prototype.RocketSilo, self.get_entity(Prototype.RocketSilo, silo_position)
        )
