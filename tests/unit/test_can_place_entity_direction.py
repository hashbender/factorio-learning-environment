"""can_place_entity checks the direction it is asked about. Server-free.

The client used to send ``direction.value + 1`` and the action mapped every
non-inserter to north (and every inserter to east), so the answer ignored
the direction. The action is run here in Lua (lupa) against a stub surface.
"""

from pathlib import Path

import pytest

from fle.env.entities import Direction, Position
from fle.env.game_types import Prototype
from fle.env.tools.agent.can_place_entity.client import CanPlaceEntity

lupa = pytest.importorskip("lupa")

SERVER_LUA = (
    Path(__file__).resolve().parents[2]
    / "fle/env/tools/agent/can_place_entity/server.lua"
)

# A 3x5 entity (steam engine) at the origin; the stub surface records each call
STUB_LUA = """
defines = {direction = {north = 0, east = 4, south = 8, west = 12}}
prototypes = {entity = {["steam-engine"] = {
    type = "generator", tile_width = 3, tile_height = 5,
    collision_box = {left_top = {x = -1.5, y = -2.5}, right_bottom = {x = 1.5, y = 2.5}}}}}
calls = {placed = {}}
local surface = {is_chunk_generated = function() return true end}
local player = {
    valid = true,
    position = {x = 20, y = 20}, reach_distance = 100, surface = surface,
    force = {is_chunk_charted = function() return true end},
    get_item_count = function() return 1 end,
    teleport = function() end,
}
storage = {actions = {}, agent_characters = {player}, utils = {
    -- place_entity's mapping; identity is enough to see which direction arrives
    get_entity_direction = function(entity, direction) return direction end,
    ensure_valid_character = function() return player end,
    can_place_entity = function(p, entity, position, direction)
        table.insert(calls.placed, direction)
        return true
    end,
}}
"""


def _run(direction):
    lua = lupa.LuaRuntime()
    lua.execute(STUB_LUA)
    lua.execute(SERVER_LUA.read_text())
    result = lua.eval("storage.actions.can_place_entity")(
        1, "steam-engine", direction, 0, 0
    )
    assert result.fits and result.can_place
    calls = lua.eval("calls")
    placed = [calls.placed[i] for i in range(1, len(calls.placed) + 1)]
    f = result.footprint
    return placed, (f.right - f.left + 1, f.bottom - f.top + 1)


@pytest.mark.parametrize(
    "direction, footprint",
    [
        (Direction.UP, (3, 5)),
        (Direction.RIGHT, (5, 3)),
        (Direction.DOWN, (3, 5)),
        (Direction.LEFT, (5, 3)),
    ],
)
def test_action_checks_requested_direction(direction, footprint):
    placed, size = _run(direction.value)
    assert placed == [direction.value]
    assert size == footprint


def test_client_sends_factorio_direction():
    tool = CanPlaceEntity.__new__(CanPlaceEntity)
    tool.player_index = 1
    sent = []

    def execute(*args):
        sent.append(args)
        return True, 0

    tool.execute = execute
    for direction in (Direction.UP, Direction.RIGHT, Direction.DOWN, Direction.LEFT):
        assert tool(Prototype.SteamEngine, direction, Position(x=0.5, y=0.5))
    assert [args[2] for args in sent] == [0, 4, 8, 12]
