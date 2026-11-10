"""connect_entities belt guard: snapshot parsing, diffing, rollback and the error. Server-free."""

import pytest

from fle.env.entities import Position
from fle.env.tools.agent.connect_entities import belt_guard
from fle.env.tools.agent.connect_entities.belt_guard import BeltState
from fle.env.tools.agent.connect_entities.client import ConnectEntities

BEFORE = "belts:0.5,0.5,transport-belt,4,-,-;1.5,0.5,underground-belt,4,input,5.5:0.5"


def test_parse_snapshot():
    belts = belt_guard.parse_snapshot(BEFORE)
    assert belts == {
        (0.5, 0.5): BeltState("transport-belt", 4),
        (1.5, 0.5): BeltState("underground-belt", 4, "input", "5.5:0.5"),
    }
    assert belt_guard.parse_snapshot("belts:") == {}
    assert belt_guard.parse_snapshot("error") is None


def test_changed_and_new_belts():
    before = belt_guard.parse_snapshot(BEFORE)
    after = dict(before)
    after[(0.5, 0.5)] = BeltState("transport-belt", 8)  # turned
    del after[(1.5, 0.5)]  # removed
    after[(0.5, 1.5)] = BeltState("transport-belt", 8)  # placed by the call
    changes = belt_guard.changed_belts(before, after)
    assert [c[0] for c in changes] == [(0.5, 0.5), (1.5, 0.5)]
    assert belt_guard.new_belts(before, after) == [
        ((0.5, 1.5), BeltState("transport-belt", 8))
    ]
    message = belt_guard.conflict_message(changes, rolled_back=True)
    assert (
        "transport-belt at (0.5, 0.5) facing RIGHT would be turned to face DOWN"
        in message
    )
    assert "underground-belt at (1.5, 0.5) facing RIGHT would be removed" in message
    assert "Nothing was built" in message and "allow_belt_changes=True" in message


def test_rollback_command_restores_and_picks_up():
    before = belt_guard.parse_snapshot(BEFORE)
    after = {
        (0.5, 0.5): BeltState("transport-belt", 8),
        (0.5, 1.5): BeltState("transport-belt", 8),
    }
    lua = belt_guard.rollback_command(1, before, after)
    assert (
        "find_entity('transport-belt', {0.5, 1.5}) if e then e.destroy() c.insert"
        in lua
    )
    assert "if e.direction ~= 4 then e.direction = 4 end" in lua
    assert (
        "create_entity{name = 'underground-belt', position = {1.5, 0.5}, direction = 4, force = c.force, type = 'input'}"
        in lua
    )


class _Rcon:
    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []

    def send_command(self, command):
        self.sent.append(command)
        return self.replies.pop(0)


def _tool(replies):
    tool = ConnectEntities.__new__(ConnectEntities)
    tool.player_index = 1
    tool.connection = type("C", (), {"rcon_client": _Rcon(replies)})()
    tool._protected_box = (0, 0, 1, 1)
    tool._protected_belts = belt_guard.parse_snapshot(BEFORE)
    return tool


def test_check_passes_when_existing_belts_are_unchanged():
    tool = _tool([BEFORE + ";9.5,9.5,transport-belt,0,-,-"])
    tool._check_protected_belts()  # a new belt alone is fine
    assert len(tool.connection.rcon_client.sent) == 1


def test_check_rolls_back_and_names_the_belt():
    turned = "belts:0.5,0.5,transport-belt,8,-,-;1.5,0.5,underground-belt,4,input,5.5:0.5;0.5,1.5,transport-belt,8,-,-"
    tool = _tool([turned, "", BEFORE])
    with pytest.raises(
        Exception,
        match=r"transport-belt at \(0.5, 0.5\) facing RIGHT would be turned to face DOWN. Nothing was built",
    ):
        tool._check_protected_belts()
    rollback = tool.connection.rcon_client.sent[1]
    assert "e.destroy()" in rollback and "e.direction = 4" in rollback


def test_rotate_end_belt_skips_existing_belts():
    tool = _tool([])
    tool._protected_belts = {(0.5, 0.5): BeltState("transport-belt", 4)}

    class Belt:
        position = Position(x=0.5, y=0.5)

    class Next:
        position = Position(x=0.5, y=1.5)

    group = type("G", (), {"outputs": [Belt()]})()
    target = type("G", (), {"inputs": [Next()]})()
    tool.rotate_entity = lambda *a: pytest.fail("existing belt was rotated")
    assert tool.rotate_end_belt_to_face(group, target) is group
