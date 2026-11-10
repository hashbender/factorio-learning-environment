"""rotate_entity and pickup_entity send the reach flag to the game. Server-free."""

from fle.env.entities import BurnerInserter, Direction, Position
from fle.env.game_types import Prototype
from fle.env.tools.agent.pickup_entity.client import PickupEntity
from fle.env.tools.agent.rotate_entity.client import RotateEntity


def _tool(cls, reply):
    tool = cls.__new__(cls)
    tool.player_index = 1
    tool.check_reach = True
    tool.calls = []

    def execute(*args):
        tool.calls.append(args)
        return reply, 0

    tool.execute = execute
    return tool


def test_pickup_checks_reach_by_default():
    tool = _tool(PickupEntity, {})
    assert tool(Prototype.WoodenChest, Position(x=1, y=2))
    assert tool.calls == [(1, 1, 2, "wooden-chest", True)]


def test_pickup_reach_can_be_turned_off():
    tool = _tool(PickupEntity, {})
    tool.check_reach = False
    assert tool(Prototype.WoodenChest, Position(x=1, y=2))
    assert tool.calls[0][-1] is False


def test_rotate_sends_reach_flag():
    # model_construct: only name and position are read before the call
    inserter = BurnerInserter.model_construct(
        name="burner-inserter",
        position=Position(x=0.5, y=0.5),
        direction=Direction.UP,
        prototype=Prototype.BurnerInserter,
    )
    tool = _tool(RotateEntity, {})
    tool.check_reach = False
    try:
        tool(inserter, Direction.RIGHT)
    except Exception:
        pass  # the stub reply is not an entity; only the call matters here
    assert tool.calls and tool.calls[0][-1] is False
