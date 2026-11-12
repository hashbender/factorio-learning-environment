from typing import Union

from fle.env.entities import BeltGroup, Entity, EntityGroup, Position
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
        if isinstance(source, BeltGroup):
            return self._from_belts(entity, source, quantity)
        if isinstance(source, Position):
            x, y = self.get_position(source)

        elif isinstance(source, Entity):
            x, y = self.get_position(source.position)
            source_name = source.name
        else:
            kind = "an EntityGroup" if isinstance(source, EntityGroup) else type(source).__name__
            raise TypeError(
                "extract_item: source must be an Entity, a Position or a BeltGroup, "
                f"got {kind}{'' if source is not None else ' (None)'}"
            )

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

    @staticmethod
    def _holds(belt, item: str) -> bool:
        """True if the belt's lanes list the item (or its contents are not known)."""
        inv = getattr(belt, "inventory", None)
        if not isinstance(inv, dict):
            return True
        lanes = [inv.get("left"), inv.get("right")] if ("left" in inv or "right" in inv) else [inv]
        return any(isinstance(lane, dict) and (lane.get(item) or 0) > 0 for lane in lanes)

    def _from_belts(self, entity: Prototype, group: BeltGroup, quantity: int) -> int:
        """A BeltGroup: the item comes off the belts of the group that carry it, in order,
        until `quantity` are taken."""
        name, _ = entity.value
        got = 0
        errors = []
        for belt in [b for b in group.belts if self._holds(b, name)]:
            if got >= quantity:
                break
            try:
                got += int(self(entity, belt, quantity - got))
            except Exception as e:  # noqa: BLE001
                errors.append(str(e))
        if got < 1:
            detail = f": {errors[0]}" if errors else ": no belt of the group carries it"
            raise Exception(f"Could not extract {name} from the belt group{detail}")
        return got
