from fle.env import DirectionInternal
from fle.env import entities as ent
from fle.env.game_types import Prototype
from fle.env.tools import Tool


class PreviewInserter(Tool):
    def __init__(self, *args):
        super().__init__(*args)

    def __call__(
        self,
        entity: Prototype,
        direction: ent.Direction = ent.Direction.UP,
        position: ent.Position = ent.Position(x=0, y=0),
    ) -> ent.InserterPreview:
        """
        Shows what an inserter would take from and drop into if placed at a
        position and direction, without placing it (no item needed).
        :param entity: Inserter prototype, e.g. Prototype.BurnerInserter
        :param direction: Direction as for place_entity
        :param position: Position to place the inserter
        :return: InserterPreview with the pickup and drop positions and the
            entity at each (None: nothing an inserter can use there)
        """
        if not isinstance(entity, Prototype):
            raise ValueError(
                "The first argument must be a Prototype, e.g. Prototype.BurnerInserter"
            )
        if isinstance(position, tuple):
            position = ent.Position(x=position[0], y=position[1])
        if not isinstance(position, ent.Position):
            raise ValueError("The position argument must be a Position object")
        if not isinstance(direction, (DirectionInternal, ent.Direction)):
            raise ValueError("The direction argument must be a Direction object")

        name, _ = entity.value
        x, y = self.get_position(position)
        factorio_direction = DirectionInternal.to_factorio_direction(direction)
        response, _elapsed = self.execute(
            self.player_index, name, factorio_direction, x, y
        )
        if not isinstance(response, dict):
            raise Exception(
                f"Could not preview {name}: {self.get_error_message(str(response))}"
            )
        data = self.clean_response(response)
        if isinstance(direction, ent.Direction):
            data["direction"] = direction
        return ent.InserterPreview(**data)
