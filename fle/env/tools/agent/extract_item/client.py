from typing import Union

from fle.env.entities import Position, Entity
from fle.env.game_types import Prototype
from fle.env.tools import Tool


class ExtractItem(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)

    def __call__(
        self, entity: Prototype, source: Union[Position, Entity], quantity=5
    ) -> int:
        """
        Extract an item from the inventory of the entity at a position (or the given entity).
        Items come only from the entity that occupies the position, never from a neighbour;
        if no entity is there, or it does not hold the item, an error names the nearest
        entities (within 10 tiles) that hold it.
        :param entity: Entity prototype to extract, e.g Prototype.IronPlate
        :param source: Entity or position to extract from (a belt there: items come off its lanes)
        :param quantity: Quantity to extract
        :example extract_item(Prototype.IronPlate, stone_furnace.position, 5)
        :example extract_item(Prototype.CopperCable, stone_furnace, 5)
        :return The number of items extracted.
        """
        source_name = None
        if isinstance(source, Position):
            x, y = self.get_position(source)

        elif isinstance(source, Entity):
            x, y = self.get_position(source.position)
            source_name = source.name

        name, _ = entity.value

        response, elapsed = self.execute(
            self.player_index, name, quantity, x, y, source_name
        )
        if isinstance(response, str):
            msg = self.get_error_message(response)
            if source_name:
                raise Exception(
                    f"Could not extract {name} from {source_name} at ({x}, {y}): {msg}"
                )
            else:
                raise Exception(f"Could not extract {name} at ({x}, {y}): {msg}")

        if not isinstance(response, (int, float)) or response < 1:
            where = f" from {source_name}" if source_name else ""
            raise Exception(
                f"Could not extract {name}{where} at ({x}, {y}): the game returned"
                f" {response!r} instead of an item count"
            )

        return response
