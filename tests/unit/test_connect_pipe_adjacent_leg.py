"""connect_entities: a pipe leg whose ends are the same tile or side by side is built
directly, on the start tile and the end tile, without the game's path search.
Server-free (lupa, fake surface).

Before, such a leg (e.g. from the pipe a previous leg ended on to a refinery port just
above it) could not start on its own tile, and the search from a neighbouring tile went
round the existing pipe and back: 7 pipes in a ring instead of 1.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from fle.env.entities import IndexedPosition
from fle.env.tools.agent.connect_entities.resolvers.fluid_connection_resolver import (
    FluidConnectionResolver,
)

lupa = pytest.importorskip("lupa")

SERVER_LUA = (
    Path(__file__).resolve().parents[2]
    / "fle/env/tools/agent/connect_entities/server.lua"
).read_text()

FAKE = """
local pipes = ...
local function key(p) return p.x .. "," .. p.y end
local function pipe_at(p)
    if pipes[key(p)] then return {name = "pipe", valid = true, position = {x = p.x, y = p.y}} end
    return nil
end
local surface = {}
function surface.find_entities_filtered(args)
    local p = args.position
    if p and pipe_at(p) then return {pipe_at(p)} end
    return {}
end
function surface.find_entity(name, p) if name == "pipe" then return pipe_at(p) end return nil end
function surface.can_place_entity(args) return pipe_at(args.position) == nil end
function surface.get_tile(x, y) return {name = "grass-1"} end
game = {surfaces = {[1] = surface}}
defines = {inventory = {character_main = 1}}
rendering = {draw_circle = function() end, draw_line = function() end}
local player = {valid = true, position = {x = 0, y = 0}, surface = surface, force = "player"}
function player.teleport(p) end
function player.get_inventory(_) return {get_item_count = function() return 100 end} end
storage = {
    actions = {}, paths = {}, elapsed_ticks = 0, agent_characters = {[1] = player},
    utils = {
        get_closest_entity = function() return nil end,
        calculate_movement_ticks = function() return 0 end,
        get_entity_direction = function(_, d) return d end,
        serialize_entity = function(e) return {name = e.name, position = e.position} end,
        get_direction = function(a, b)
            local dx, dy = b.x - a.x, b.y - a.y
            if math.abs(dx) > math.abs(dy) then return dx > 0 and 4 or 12 end
            return dy > 0 and 8 or 0
        end,
    },
}
"""


def _lua(pipes=()):
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(FAKE, lua.table_from({f"{x},{y}": True for x, y in pipes}))
    lua.execute(SERVER_LUA)
    return lua


def _leg(lua, types, start, end):
    path = lua.eval(
        "function(t, sx, sy, ex, ey) return storage.utils.adjacent_pipe_leg(t, {x = sx, y = sy}, {x = ex, y = ey}) end"
    )(lua.table_from(types), *start, *end)
    if path is None:
        return None
    return [(path[i].position.x, path[i].position.y) for i in range(1, len(path) + 1)]


def test_leg_to_the_tile_beside_the_start_is_those_two_tiles():
    lua = _lua()
    assert _leg(lua, ["pipe"], (18.5, 10.5), (18.5, 9.5)) == [(18.5, 10.5), (18.5, 9.5)]
    assert _leg(lua, ["pipe", "pipe-to-ground"], (3.5, 4.5), (4.5, 4.5)) == [
        (3.5, 4.5),
        (4.5, 4.5),
    ]


def test_leg_ending_on_its_start_tile_is_that_tile():
    assert _leg(_lua(), ["pipe"], (18.5, 9.5), (18.5, 9.5)) == [(18.5, 9.5)]


def test_other_legs_use_the_path_search():
    lua = _lua()
    assert _leg(lua, ["pipe"], (18.5, 11.5), (18.5, 9.5)) is None  # two tiles
    assert _leg(lua, ["pipe"], (18.5, 10.5), (19.5, 9.5)) is None  # diagonal
    assert _leg(lua, ["transport-belt"], (0.5, 0.5), (1.5, 0.5)) is None
    assert _leg(lua, ["pipe-to-ground"], (0.5, 0.5), (1.5, 0.5)) is None


def _connect(lua, start, end, dry_run, path="not_found"):
    lua.eval("function(p) storage.paths[7] = p end")(path)
    answer = lua.eval(
        "function(sx, sy, ex, ey, dry) return storage.actions.connect_entities(1, sx, sy, ex, ey, 7, 'pipe,pipe-to-ground', dry, 100) end"
    )(*start, *end, dry_run)
    planned = answer.planned
    tiles = (
        [(planned[i].x, planned[i].y) for i in range(1, len(planned) + 1)]
        if planned
        else []
    )
    return answer.number_of_entities, tiles


def test_last_leg_from_the_previous_pipe_places_one_pipe_on_the_port():
    # the previous leg ended on (18.5, 10.5); the refinery port is the tile above it
    lua = _lua(pipes=[(17.5, 10.5), (18.5, 10.5)])
    assert _connect(lua, (18.5, 10.5), (18.5, 9.5), dry_run=True) == (1, [(18.5, 9.5)])


def test_adjacent_leg_ignores_a_detour_from_the_path_search():
    lua = _lua(pipes=[(18.5, 10.5)])
    detour = lua.eval(
        "{ {position={x=18.5,y=11.5}}, {position={x=20.5,y=11.5}}, {position={x=20.5,y=9.5}}, {position={x=18.5,y=9.5}} }"
    )
    assert _connect(lua, (18.5, 10.5), (18.5, 9.5), dry_run=True, path=detour) == (
        1,
        [(18.5, 9.5)],
    )


def test_leg_from_an_empty_start_tile_beside_the_port_plans_both_tiles():
    lua = _lua()
    count, tiles = _connect(lua, (18.5, 10.5), (18.5, 9.5), dry_run=True)
    assert count == 2 and sorted(tiles) == [(18.5, 9.5), (18.5, 10.5)]


def test_one_tile_leg_on_the_port_plans_one_pipe():
    lua = _lua(pipes=[(18.5, 10.5)])
    assert _connect(lua, (18.5, 9.5), (18.5, 9.5), dry_run=True) == (1, [(18.5, 9.5)])


def _refinery():
    return SimpleNamespace(
        recipe="basic-oil-processing",
        name="oil-refinery",
        position=(17.5, 6.5),
        input_connection_points=[IndexedPosition(x=18.5, y=9.5, type="crude-oil")],
    )


def test_recipe_check_accepts_a_bare_position_as_source():
    resolver = FluidConnectionResolver.__new__(FluidConnectionResolver)
    source = [IndexedPosition(x=18.5, y=10.5, type="all")]
    assert resolver.check_for_recipe_requirement(_refinery(), source) is True


def test_recipe_check_still_refuses_the_wrong_fluid():
    resolver = FluidConnectionResolver.__new__(FluidConnectionResolver)
    source = [IndexedPosition(x=18.5, y=10.5, type="water")]
    with pytest.raises(Exception, match="not needed"):
        resolver.check_for_recipe_requirement(_refinery(), source)
