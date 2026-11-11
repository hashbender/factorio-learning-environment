"""A connect_entities dry run reports each underground entity with the direction the tool API
(place_entity / place_layout) takes, and its type (input/output).

Before, it reported the game's own direction. For pipe-to-ground the API direction is turned
round (get_entity_direction), so a plan built back through place_layout had every pair facing
away from each other: an agent's 587-tile crude pipeline was broken at each pair.
"""

from pathlib import Path

import pytest

from fle.env.entities import Direction
from fle.env.tools.agent.connect_entities import dry_run

lupa = pytest.importorskip("lupa")

SERVER_LUA = (
    Path(__file__).resolve().parents[2]
    / "fle/env/tools/agent/connect_entities/server.lua"
).read_text()

FAKE = """
game = {surfaces = {}}
defines = {inventory = {character_main = 1}}
rendering = {draw_circle = function() end, draw_line = function() end}
-- as mods/serialize.lua: pipe-to-ground is turned round, underground belts are not
local flip = {[0] = 8, [4] = 12, [8] = 0, [12] = 4}
storage = {actions = {}, paths = {}, agent_characters = {}, utils = {
    get_entity_direction = function(name, d)
        if name == "pipe-to-ground" then return flip[d] end
        return d
    end,
}}
"""


def _lua():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(FAKE)
    lua.execute(SERVER_LUA)
    return lua


@pytest.mark.parametrize("api", [0, 4, 8, 12])
def test_reported_direction_builds_the_same_pipe_to_ground(api):
    lua = _lua()
    to_game = lua.eval("storage.utils.get_entity_direction")
    to_api = lua.eval("storage.utils.connect_api_direction")
    game = to_game("pipe-to-ground", api)
    assert game != api  # the API direction is turned round for pipe-to-ground
    reported = to_api("pipe-to-ground", game)
    assert to_game("pipe-to-ground", reported) == game


def test_underground_belt_direction_unchanged():
    lua = _lua()
    to_api = lua.eval("storage.utils.connect_api_direction")
    for d in (0, 4, 8, 12):
        assert to_api("underground-belt", d) == d


def test_plan_carries_the_underground_type():
    planned = dry_run.planned_entities(
        [
            {"name": "pipe-to-ground", "x": 0.5, "y": 0.5, "direction": 12, "type": "input"},
            {"name": "pipe-to-ground", "x": 5.5, "y": 0.5, "direction": 4, "type": "output"},
            {"name": "pipe", "x": 6.5, "y": 0.5, "direction": 0},
        ]
    )
    assert [p.type for p in planned] == ["input", "output", None]
    assert planned[0].direction == Direction.LEFT
    assert "input" in repr(planned[0])
