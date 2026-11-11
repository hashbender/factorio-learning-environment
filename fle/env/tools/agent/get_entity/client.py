from time import sleep

from fle.env.entities import Position, Entity

from fle.env.game_types import Prototype
from fle.env.tools.agent.get_entities.client import GetEntities
from fle.env.tools import Tool


class GetEntity(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)
        self.get_entities = GetEntities(connection, game_state)

    def __call__(self, entity: Prototype, position: Position) -> Entity:
        """
        Get the entity of the given prototype that occupies position (x, y).
        The position must lie on one of the entity's tiles (any tile of a multi-tile entity works);
        a neighbouring entity is never returned. Raises an error naming up to 3 of the nearest
        entities of that prototype when none occupies the position.
        :param entity: Entity prototype to get, e.g Prototype.StoneFurnace
        :param position: Position on one of the entity's tiles
        :return: Entity object
        """
        assert isinstance(entity, Prototype)
        assert isinstance(position, Position)
        if entity == Prototype.BeltGroup:
            entities = self.get_entities(
                {
                    Prototype.TransportBelt,
                    Prototype.FastTransportBelt,
                    Prototype.ExpressTransportBelt,
                },
                position=position,
            )
            return entities[0] if len(entities) > 0 else None
        elif entity == Prototype.PipeGroup:
            entities = self.get_entities({Prototype.Pipe}, position=position)
            return entities[0] if len(entities) > 0 else None
        elif entity == Prototype.ElectricityGroup:
            entities = self.get_entities(
                {
                    Prototype.SmallElectricPole,
                    Prototype.MediumElectricPole,
                    Prototype.BigElectricPole,
                },
                position=position,
            )
            return entities[0] if len(entities) > 0 else None
        else:
            x, y = self.get_position(position)
            name, metaclass = entity.value
            while isinstance(metaclass, tuple):
                metaclass = metaclass[1]

            sleep(0.05)
            response, elapsed = self.execute(self.player_index, name, x, y)

            if isinstance(response, str):
                # The server's reason: no entity of this prototype occupies the
                # position (with the nearest ones), or an unknown prototype.
                raise Exception(self.get_error_message(response))
            if response is None or response == {}:
                raise Exception(
                    f"Could not get {name} at position ({x}, {y}): no response from the game"
                )

            try:
                cleaned_response = self.clean_response(response)
                object = metaclass(prototype=entity.name, **cleaned_response)
            except Exception as e:
                raise Exception(
                    f"Could not get {name} at position ({x}, {y}): could not create the "
                    f"{name} object from the response ({e})"
                ) from e

            return object
