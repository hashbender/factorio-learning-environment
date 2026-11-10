from typing import Any

from fle.env import DirectionInternal
from fle.env import entities as ent
from fle.env.game_types import Prototype
from fle.env.tools import Tool


def _as_list(value: Any) -> list:
    """Lua sequences can arrive as lists or as {1: ..., 2: ...} dicts."""
    if isinstance(value, dict):
        return [value[k] for k in sorted(value, key=lambda k: int(k))]
    return list(value or [])


def _number(value: float) -> str:
    return f"{value:g}"


def placement_check(name: str, direction, response: dict) -> ent.PlacementCheck:
    """Build the PlacementCheck for the action's answer."""
    fits = bool(response.get("fits"))
    in_reach = bool(response.get("in_reach", True))
    in_inventory = int(response.get("in_inventory") or 0)
    blocked_by = [
        ent.PlacementBlocker(
            kind=str(b.get("kind", "entity")),
            name=str(b["name"]),
            position=ent.Position(x=b["x"], y=b["y"]),
        )
        for b in _as_list(response.get("blocked_by"))
    ]
    reason = response.get("reason")
    if fits:
        # It fits: say what place_entity would still refuse it for
        missing = []
        if not in_reach:
            missing.append(
                f"out of reach (distance {_number(response.get('distance', 0))}, "
                f"reach {_number(response.get('reach', 0))})"
            )
        if in_inventory <= 0:
            missing.append(f"no {name} in your inventory")
        reason = "fits, but " + " and ".join(missing) if missing else None
    position = response.get("position") or {}
    return ent.PlacementCheck(
        entity=name,
        position=ent.Position(x=position.get("x", 0), y=position.get("y", 0)),
        direction=direction if isinstance(direction, ent.Direction) else None,
        can_place=fits and in_reach and in_inventory > 0,
        fits=fits,
        reason=str(reason) if reason else None,
        blocked_by=blocked_by,
        blocked_count=int(response.get("blocked_count") or len(blocked_by)),
        in_reach=in_reach,
        distance=response.get("distance"),
        reach=response.get("reach"),
        in_inventory=in_inventory,
    )


class CanPlaceEntity(Tool):
    def __init__(self, *args):
        super().__init__(*args)

    def __call__(
        self,
        entity: Prototype,
        direction: ent.Direction = ent.Direction.UP,
        position: ent.Position = ent.Position(x=0, y=0),
    ) -> ent.PlacementCheck:
        """
        Asks the game whether an entity can be built at a position and direction, without building it.
        Builds nothing, needs no item in the inventory, takes no game time and works at any distance.
        :param entity: Entity to check
        :param direction: Direction as for place_entity
        :param position: Position as for place_entity
        :return: PlacementCheck. It is True in an `if` when place_entity would build the entity now
            (it fits, is in reach and is in your inventory). Fields: fits (the game's build check),
            reason and blocked_by (what is in the way, with positions), position (where it would be
            built), in_reach, in_inventory.
        """

        assert isinstance(entity, Prototype)
        assert isinstance(direction, ent.Direction)

        # If position is a tuple, cast it to a Position object:
        if isinstance(position, tuple):
            position = ent.Position(x=position[0], y=position[1])

        assert isinstance(position, ent.Position)

        x, y = self.get_position(position)
        name, metaclass = entity.value

        # Same direction encoding as place_entity (Factorio 2.0: 0, 4, 8, 12)
        factorio_direction = DirectionInternal.to_factorio_direction(direction)
        response, elapsed = self.execute(
            self.player_index, name, factorio_direction, x, y
        )

        if isinstance(response, dict) and "fits" in response:
            return placement_check(name, direction, response)
        if isinstance(response, bool):
            return ent.PlacementCheck(
                entity=name,
                position=position,
                direction=direction,
                can_place=response,
                fits=response,
                in_inventory=1 if response else 0,
            )
        raise Exception(
            f"Could not check placement of {name}: {self.get_error_message(str(response))}"
        )
