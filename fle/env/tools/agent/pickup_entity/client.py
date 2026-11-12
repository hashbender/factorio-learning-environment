import re
from typing import List, Union, Optional

from fle.env import entities as ent
from fle.env.game_types import Prototype
from fle.env.tools import Tool


_NAME = re.compile(r"[a-z0-9-]{1,100}")
_UNDERGROUND_BELTS = ("underground-belt", "fast-underground-belt", "express-underground-belt")


class PickedUp:
    """The answer of pickup_entity for an underground belt: true, and says what was
    picked up (both ends of a linked pair, or the one end)."""

    def __init__(self, picked: List[str], problem: Optional[str] = None):
        self.picked = list(picked)
        self.problem = problem

    def __bool__(self) -> bool:
        return True

    def __eq__(self, other) -> bool:
        if isinstance(other, bool):
            return other is True
        return NotImplemented

    __hash__ = None

    def __repr__(self) -> str:
        text = "Picked up " + " and ".join(self.picked)
        return text + (f"; {self.problem}" if self.problem else "")

    __str__ = __repr__


class PickupEntity(Tool):
    def __init__(self, *args):
        super().__init__(*args)
        # Picking up needs the entity within the character's reach. Tools that
        # remove entities they have just built themselves (connect_entities)
        # turn this off.
        self.check_reach = True

    def __call__(
        self,
        entity: Union[ent.Entity, Prototype, ent.EntityGroup],
        position: Optional[ent.Position] = None,
    ) -> bool:
        """
        Pick up an entity if it exists on the world at a given position.
        :param entity: Entity prototype to pickup, e.g Prototype.IronPlate
        :param position: Position to pickup entity
        :return: True if the entity was picked up successfully, False otherwise.
        """
        if not isinstance(entity, (Prototype, ent.Entity, ent.EntityGroup)):
            raise ValueError("The first argument must be an Entity or Prototype object")
        if isinstance(entity, ent.Entity) and isinstance(position, ent.Position):
            raise ValueError(
                "If the first argument is an Entity object, the second argument must be None"
            )
        if position is not None and not isinstance(position, ent.Position):
            raise ValueError("The second argument must be a Position object")

        if isinstance(entity, Prototype):
            name, _ = entity.value
        else:
            name = entity.name
            if isinstance(entity, ent.BeltGroup):
                belts = entity.belts
                for belt in belts:
                    resp = self.__call__(belt)
                    if not resp:
                        return False
                return True
            elif isinstance(entity, ent.PipeGroup):
                pipes = entity.pipes
                for pipe in pipes:
                    resp = self.__call__(pipe)
                    if not resp:
                        return False
                return True

            elif isinstance(entity, ent.ElectricityGroup):
                poles = entity.poles
                for pole in poles:
                    resp = self.__call__(pole)
                    if not resp:
                        return False
                return True

        if name in _UNDERGROUND_BELTS and (
            position or isinstance(entity, ent.Entity)
        ):
            # Both ends of a pair the game links; an unpaired end alone. Nothing else.
            # (By entity or by prototype and position alike.)
            x, y = (position.x, position.y) if position else (
                entity.position.x,
                entity.position.y,
            )
            partner = self._underground_partner(name, x, y)
            response, elapsed = self.execute(
                self.player_index, x, y, name, self.check_reach
            )
            if response != 1 and response != {}:
                raise Exception(f"Could not pickup: {self.get_error_message(response)}")
            picked = [f"{name} at ({x}, {y})"]
            if partner is None:
                return PickedUp(picked)
            px, py = partner
            try:
                response, elapsed = self.execute(
                    self.player_index, px, py, name, self.check_reach
                )
            except Exception as e:  # noqa: BLE001
                response = str(e)
            if response == 1 or response == {}:
                picked.append(f"its paired {name} at ({px}, {py})")
                return PickedUp(picked)
            return PickedUp(
                picked,
                f"its paired {name} at ({px}, {py}) was not picked up: "
                f"{self.get_error_message(response)}",
            )

        elif position:
            x, y = position.x, position.y
            response, elapsed = self.execute(
                self.player_index, x, y, name, self.check_reach
            )
        elif isinstance(entity, ent.Entity):
            x, y = entity.position.x, entity.position.y
            response, elapsed = self.execute(
                self.player_index, x, y, name, self.check_reach
            )
        else:
            raise ValueError("The second argument must be a Position object")

        if response != 1 and response != {}:
            raise Exception(f"Could not pickup: {self.get_error_message(response)}")
        return True

    def _underground_partner(self, name: str, x: float, y: float):
        """The position of the underground belt the game links to the one at (x, y), or None."""
        if not _NAME.fullmatch(name or ""):
            return None
        try:
            answer = self.connection.rcon_client.send_command(
                f"/sc local e = game.surfaces[1].find_entities_filtered{{name = '{name}', "
                f"position = {{{float(x)}, {float(y)}}}, radius = 0.5}}[1]; "
                "local n = e and e.neighbours; "
                "if n and n.valid then rcon.print(n.position.x .. ',' .. n.position.y) "
                "else rcon.print('none') end"
            )
        except Exception:  # noqa: BLE001
            return None
        text = (answer or "").strip()
        if not text or text == "none":
            return None
        try:
            px, py = (float(v) for v in text.split(","))
        except ValueError:
            return None
        return px, py
